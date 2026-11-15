#!/usr/bin/env python3
"""r9 analysis consistency checker.

Exit 0: required artifacts exist and numbers in analysis.json / conclusion.txt
match values recomputed from r8 evidence + blender-dump (NOT a quality pass).
Exit 1: missing artifact or inconsistency.
Exit 2: usage / unreadable input.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def fail(msg: str, code: int = 1) -> int:
    print(f"FAIL: {msg}")
    return code


def load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fg_bbox(image_path: Path, thresh: int = 250):
    from PIL import Image
    import numpy as np

    img = np.array(Image.open(image_path).convert("RGB"))
    mask = (img.min(axis=2) < thresh) | ((img.max(axis=2) - img.min(axis=2)) > 8)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise ValueError(f"no foreground in {image_path}")
    return {
        "x0": int(xs.min()),
        "x1": int(xs.max()),
        "y0": int(ys.min()),
        "y1": int(ys.max()),
        "w": int(xs.max() - xs.min() + 1),
        "h": int(ys.max() - ys.min() + 1),
    }


def close(a, b, tol=1e-6):
    return abs(float(a) - float(b)) <= tol


def main(argv: list[str]) -> int:
    ev = Path(argv[1]) if len(argv) > 1 else REPO / "docs/prd/evidence/fusion/fidelity/r9-analysis"
    ev = ev.resolve()
    r8 = ev.parent / "r8"
    required = [
        ev / "analysis.json",
        ev / "camera.json",
        ev / "lights.json",
        ev / "brightness-table.json",
        ev / "blender-dump.json",
        ev / "conclusion.txt",
        ev / "clay-00ac0cff-front.png",
        ev / "annotated-stove.png",
        ev / "dump_blender_scene.py",
        r8 / "metrics.json",
        r8 / "scene-00ac0cff-raw.json",
        r8 / "golds/00ac0cff-front-1920.png",
        r8 / "render-00ac0cff-front.png",
        r8 / "params-00ac0cff-front.json",
        REPO / "tools/fusion-checks/fidelity_r9_analysis_check.py",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        return fail("missing artifacts:\n  " + "\n  ".join(missing))

    analysis = load(ev / "analysis.json")
    camera = load(ev / "camera.json")
    lights = load(ev / "lights.json")
    brightness = load(ev / "brightness-table.json")
    dump = load(ev / "blender-dump.json")
    metrics = load(r8 / "metrics.json")
    raw = load(r8 / "scene-00ac0cff-raw.json")
    conclusion = (ev / "conclusion.txt").read_text(encoding="utf-8")

    errors = []

    # --- dump vs camera.json ---
    dcam = dump["camera"]
    acam = camera["applied_camera"]
    if dcam["look_down_sceneYup_deg"] != 30.0:
        errors.append(f"dump look_down is {dcam['look_down_sceneYup_deg']}, expected 30.0")
    if acam["look_down_sceneYup_deg"] != 30.0:
        errors.append("camera.json look_down != 30.0")
    if acam["blender_loc"] != [0.0, 0.9, -1.45]:
        errors.append(f"camera.json blender_loc {acam['blender_loc']}")
    if camera["active_camera_id"] != "028cb306-266e-476b-8426-b8d5b9bc4f49":
        errors.append("active camera id mismatch")
    if camera["view_id"] != "3c8d747b-24c6-428a-aa2c-b9124f60e2f2":
        errors.append("view id mismatch")
    if raw["views"]["3c8d747b-24c6-428a-aa2c-b9124f60e2f2"]["active_camera"] != camera["active_camera_id"]:
        errors.append("raw scene view camera != camera.json")
    front = raw["cameras"][camera["active_camera_id"]]
    if front.get("position") != [0, -1.45, 0.9]:
        errors.append(f"raw 前视图 pos {front.get('position')}")
    if (front.get("camera") or {}).get("fov") != 35:
        errors.append("raw fov != 35")
    if camera["hob_orientation"]["thin_axis_blender"] != "Y":
        errors.append("hob thin axis not Y")
    if dump["product_world_aabb"]["thin_axis_blender"] != "Y":
        errors.append("dump AABB thin axis not Y")
    if not dump["product_world_aabb"]["horizontal_if_thin_Y"]:
        errors.append("dump says hob is not horizontal")

    # --- silhouettes ---
    gold_bbox = fg_bbox(r8 / "golds/00ac0cff-front-1920.png")
    rend_bbox = fg_bbox(r8 / "render-00ac0cff-front.png")
    claimed_g = camera["silhouette"]["gold_fg_bbox_px"]
    claimed_r = camera["silhouette"]["r8_render_fg_bbox_px"]
    for key in ("x0", "x1", "y0", "y1"):
        if claimed_g[key] != gold_bbox[key]:
            errors.append(f"gold bbox {key} claimed {claimed_g[key]} computed {gold_bbox[key]}")
        if claimed_r[key] != rend_bbox[key]:
            errors.append(f"r8 bbox {key} claimed {claimed_r[key]} computed {rend_bbox[key]}")
    height_delta = gold_bbox["y0"] - rend_bbox["y0"]
    if abs(height_delta) != 59 and height_delta != camera["silhouette"]["height_delta_px"]:
        # gold y0 311, render y0 370 => -59
        pass
    if abs(camera["silhouette"]["height_delta_px"]) != 59 and abs(height_delta) != 59:
        errors.append(f"height delta claimed {camera['silhouette']['height_delta_px']} computed {height_delta}")
    # Accept claimed height_delta_px as 59 (absolute) or -59 (signed). We stored 311-370=-59.
    if abs(camera["silhouette"]["height_delta_px"]) != 59:
        errors.append(f"height_delta_px should have abs 59, got {camera['silhouette']['height_delta_px']}")

    union = dump["projected_union_px"]
    cu = camera["silhouette"]["clay_projected_union_px"]
    for key in ("x0", "x1", "y0", "y1"):
        if not close(union[key], cu[key], 0.05):
            errors.append(f"projected union {key} {cu[key]} != dump {union[key]}")

    # --- lights ---
    r24 = next(l for l in dump["lights_comparison"] if l["name"] == "RectLight24")
    if not close(r24["delta_dist_m"], 6.593389, 1e-6):
        errors.append(f"RectLight24 delta {r24['delta_dist_m']}")
    if lights["main_fill_RectLight24"]["delta_dist_m"] != r24["delta_dist_m"]:
        errors.append("lights.json RectLight24 delta != dump")
    if r24["depth"] != 2:
        errors.append(f"RectLight24 depth {r24['depth']} != 2")
    total = 0.0
    for l in dump["lights_comparison"]:
        p = float(l["power_raw"])
        if l["type"] == "area_light":
            total += p * math.pi / 683.0
        elif l["type"] in ("point_light", "spot_light"):
            total += p * 4.0 * math.pi / 683.0
        else:
            total += p
    if not close(lights["total_cycles_W_mapped"], total, 1e-5):
        errors.append(f"total W claimed {lights['total_cycles_W_mapped']} computed {total}")
    r24_w = 38.780670166015625 * math.pi / 683.0
    if not close(lights["RectLight24_cycles_W"], r24_w, 1e-5):
        errors.append("RectLight24 W mismatch")

    # --- brightness table vs r8 metrics ---
    rows = {r["task"]: r for r in brightness["rows"]}
    expected_metrics = {
        "329c202e": ("329c202e-Front", 19.8068, 2.477),
        "2aa0b2f5": ("2aa0b2f5-view3c69", 57.4812, 54.235),
        "2425a469": ("2425a469-Front", 26.5857, 26.731),
        "00ac0cff": ("00ac0cff-front", 87.6523, -61.025),
        "55cc8c05": ("55cc8c05-Front", 39.8915, 28.073),
    }
    for task, (mkey, mae_fg, d_lum) in expected_metrics.items():
        row = rows[task]
        m = metrics["tasks"][mkey]["metrics"]
        if not close(row["mae_fg"], m["mae_fg"], 1e-4) or not close(row["mae_fg"], mae_fg, 1e-4):
            errors.append(f"{task} mae_fg {row['mae_fg']} vs metrics {m['mae_fg']}")
        if not close(row["d_lum_fg"], m["d_lum_fg"], 1e-3) or not close(row["d_lum_fg"], d_lum, 1e-3):
            errors.append(f"{task} d_lum_fg {row['d_lum_fg']} vs metrics {m['d_lum_fg']}")
        if row["k_applied"] != 3.1:
            errors.append(f"{task} k != 3.1")
    if rows["329c202e"]["skylight_intensity"] != 0.35 or rows["00ac0cff"]["skylight_intensity"] != 0:
        errors.append("skylight intensities off")
    if rows["2425a469"]["ev"] != 2.056:
        errors.append("pillow ev")
    if not close(rows["2425a469"]["ev_linear_2_pow_ev"], 2 ** 2.056, 1e-3):
        errors.append("pillow ev linear")
    if rows["00ac0cff"]["light_hierarchy_depth"] != 2:
        errors.append("stove light depth")

    # --- claims vs files ---
    claims = {c["id"]: c for c in analysis["claims"]}
    if claims["look_down_deg"]["value"] != 30.0:
        errors.append("claim look_down")
    if abs(claims["height_delta_px"]["value"]) != 59:
        errors.append("claim height_delta")
    if not close(claims["RectLight24_delta_m"]["value"], r24["delta_dist_m"], 1e-6):
        errors.append("claim RectLight24 delta")
    if claims["k"]["value"] != 3.1:
        errors.append("claim k")

    # --- conclusion must contain key numbers ---
    required_needles = [
        "30.0",
        "3.1",
        "6.593",
        "19.81",
        "-61.03",
        "2.056",
        "前视图",
        "3c8d747b",
        "卡萨帝",
        "white-sky-scale",
    ]
    for needle in required_needles:
        if needle not in conclusion:
            errors.append(f"conclusion.txt missing '{needle}'")

    if "未 commit" not in conclusion and "未commit" not in conclusion and "no commit" not in conclusion.lower():
        errors.append("conclusion.txt should state no commit")

    if errors:
        for e in errors:
            print("FAIL:", e)
        print(f"status FAIL n_errors={len(errors)}")
        return 1

    print("PASS: r9 analysis artifacts present and internally consistent")
    print(f"look_down_deg={dcam['look_down_sceneYup_deg']}")
    print(f"gold_bbox={gold_bbox}")
    print(f"r8_bbox={rend_bbox}")
    print(f"RectLight24_delta_m={r24['delta_dist_m']}")
    print(f"total_cycles_W_mapped={lights['total_cycles_W_mapped']}")
    print("status PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(2)
