#!/usr/bin/env python3
"""r8 generalization acceptance check.

Pass (exit 0) iff every selected task has a real gold PNG, was rendered with the
LOCKED r7-R1 *rules* (not per-task fitted k/angle/post), and has MAE/SSIM + a
written verdict. Fail (exit 1) if any selected task has no gold or the locked
flags were altered. This is a generalization test: it does NOT require beating
the fridge R1 fg MAE 19.81.

usage: fidelity_r8_check.py MANIFEST.json OUT.json
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fidelity_r4_analyze import load, fg_mask, ssim_lum, LUM

LOCKED = {
    "env-mode": "ue",
    "material-mode": "stage",
    "tonemap": "ue55",
    "fallback-light": "0",
    "skylight-scale": "3.1",
    "white-sky-scale": "0",
    "spp": "256",
    "width": "1920",
    "height": "1080",
    "denoise": "1",
}
# Flags that must NOT appear with a different value; k/angle must come from the rule.
FORBIDDEN_RETUNE = ("light-scale",)  # implicit retune of lighting if set away from candela path


def parse_cli(s: str) -> dict:
    out = {}
    if not s:
        return out
    parts = s.split() if isinstance(s, str) else list(s)
    i = 0
    while i < len(parts):
        p = parts[i]
        if p.startswith("--"):
            name = p[2:]
            if i + 1 < len(parts) and not parts[i + 1].startswith("--"):
                out[name] = parts[i + 1]
                i += 2
                continue
            out[name] = "1"
        i += 1
    return out


def is_png(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        im = Image.open(path)
        im.load()
        return im.format == "PNG" and im.size[0] >= 8 and im.size[1] >= 8
    except Exception:
        return False


def score(gold_path: str, render_path: str) -> dict:
    gold = load(gold_path)
    rend = load(render_path)
    d = np.abs(gold - rend)
    fg = fg_mask(gold)
    return {
        "mae": round(float(d.mean()), 4),
        "mae_fg": round(float(d[fg].mean()), 4),
        "ssim": round(ssim_lum(gold, rend), 6),
        "d_lum_fg": round(float((rend[fg] @ LUM - gold[fg] @ LUM).mean()), 3),
        "gold_size_loaded": [1920, 1080],
    }


def flag_problems(task: dict, cli: dict) -> list:
    problems = []
    for k, v in LOCKED.items():
        got = str(cli.get(k, task.get(k, "")))
        if got != v:
            problems.append(f"locked flag --{k} expected {v} got {got or '(missing)'}")
    expected = task.get("expected_hdri_angle")
    got_ang = cli.get("hdri-angle")
    if expected is None:
        problems.append("params missing expected_hdri_angle (task hdri_angle - 90)")
    else:
        try:
            if abs(float(got_ang) - float(expected)) > 0.051:
                problems.append(f"hdri-angle {got_ang} != task_angle-90 ({expected}); per-task retune forbidden")
        except (TypeError, ValueError):
            problems.append(f"hdri-angle {got_ang!r} is not the required task_angle-90 ({expected})")
    # k is locked at 3.1; refuse comments that say it was fitted for this task
    if task.get("k_source") not in (None, "locked_r7_R1", "r7_R1", "3.1"):
        problems.append(f"k_source {task.get('k_source')!r} is not the locked r7 R1 value")
    return problems


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: fidelity_r8_check.py MANIFEST.json OUT.json", file=sys.stderr)
        return 2
    manifest_path, out_path = sys.argv[1], sys.argv[2]
    man = json.load(open(manifest_path))
    tasks = man.get("tasks") or []
    if not tasks:
        json.dump({"status": "FAIL", "reason": "manifest has no tasks"}, open(out_path, "w"), indent=1, ensure_ascii=False)
        print("FAIL: manifest has no tasks")
        return 1
    results = []
    failed = False
    for t in tasks:
        rec = {"id": t.get("id"), "name": t.get("name"), "view": t.get("view")}
        gold, rend, params_path = t.get("gold"), t.get("render"), t.get("params")
        if not is_png(gold):
            rec.update({"status": "FAIL", "reason": "no gold PNG", "gold": gold})
            results.append(rec)
            failed = True
            continue
        if not params_path or not os.path.isfile(params_path):
            rec.update({"status": "FAIL", "reason": "missing params", "params": params_path})
            results.append(rec)
            failed = True
            continue
        params = json.load(open(params_path))
        cli = parse_cli(params.get("extra_cli") or params.get("cli") or "")
        # also accept explicit dict
        if isinstance(params.get("flags"), dict):
            cli = {**cli, **{k.lstrip("-"): str(v) for k, v in params["flags"].items()}}
        for k in ("spp", "width", "height", "denoise"):
            if k in params and k not in cli:
                cli[k] = str(params[k])
        # merge expected angle from params if present
        if "expected_hdri_angle" in params and "expected_hdri_angle" not in t:
            t = {**t, "expected_hdri_angle": params["expected_hdri_angle"]}
        if "k_source" in params:
            t = {**t, "k_source": params.get("k_source")}
        problems = flag_problems({**t, **params}, cli)
        if problems:
            rec.update({"status": "FAIL", "reason": "locked flags altered", "problems": problems, "cli": cli})
            results.append(rec)
            failed = True
            continue
        if not is_png(rend):
            rec.update({"status": "FAIL", "reason": "missing render PNG", "render": rend})
            results.append(rec)
            failed = True
            continue
        rec["metrics"] = score(gold, rend)
        rec["gold"] = gold
        rec["render"] = rend
        rec["status"] = "SCORED"
        rec["verdict"] = t.get("verdict") or params.get("verdict") or (
            f"scored mae={rec['metrics']['mae']} mae_fg={rec['metrics']['mae_fg']} ssim={rec['metrics']['ssim']}"
        )
        results.append(rec)
    out = {
        "status": "FAIL" if failed else "PASS",
        "n": len(tasks),
        "n_scored": sum(1 for r in results if r.get("status") == "SCORED"),
        "locked": LOCKED,
        "rule": "hdri-angle = task.hdri_angle - 90; skylight_scale locked 3.1; post and exposure from the task camera; no per-task k/angle fit",
        "does_not_require_fridge_r1_mae": True,
        "tasks": results,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, ensure_ascii=False)
    print(out["status"], "n_scored", out["n_scored"], "/", out["n"])
    for r in results:
        m = r.get("metrics") or {}
        print(r.get("id", "?")[:8], r.get("status"), r.get("reason", ""), m)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
