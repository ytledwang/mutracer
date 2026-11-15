#!/usr/bin/env python3
"""Fidelity comparison acceptance check. Invoked by fidelity_check.sh.

Reads docs/prd/evidence/fusion/fidelity/params.json and verifies:
  - each render PNG exists, is 1920x1080, and is non-blank
  - each render has a matching .sha256 file and a non-empty render .log
  - the comparison image exists and is non-blank
Exit 0 only if every item passes. Never git add / commit / push.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("FAIL  python deps (PIL/numpy) missing")
    sys.exit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_declared_sha(path: Path) -> str:
    text = path.read_text().strip()
    if not text:
        return ""
    return text.split()[0]


def image_ok(path: Path, expect_size=None, min_std=8.0, min_row_std=10.0, min_unique=12):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if expect_size and (w, h) != expect_size:
        return False, {
            "width": w,
            "height": h,
            "error": f"size {w}x{h} != {expect_size[0]}x{expect_size[1]}",
        }
    a = np.asarray(im, dtype=np.float32)
    lum = a.mean(axis=2)
    inner = lum[int(h * 0.1):int(h * 0.9), int(w * 0.1):int(w * 0.9)]
    stats = {
        "width": w,
        "height": h,
        "lum_mean": float(lum.mean()),
        "lum_std": float(lum.std()),
        "row_std": float(inner.std(axis=1).mean()) if inner.size else 0.0,
        "unique_lum_bins": int(len(np.unique((lum / 8).astype(np.uint8)))),
    }
    blank = (
        stats["lum_std"] < min_std
        or stats["row_std"] < min_row_std
        or stats["unique_lum_bins"] < min_unique
    )
    if blank:
        stats["error"] = "blank/flat image"
        return False, stats
    return True, stats


def resolve(ev: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ev / p


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    # Optional arg: evidence dir (e.g. docs/prd/evidence/fusion/fidelity/r2); default = round 1.
    ev = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "docs/prd/evidence/fusion/fidelity"
    params_path = ev / "params.json"
    fail = 0

    def record(ok: bool, name: str, extra: str = "") -> None:
        nonlocal fail
        if not ok:
            fail += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}")

    if not params_path.is_file():
        print(f"FAIL  params.json missing: {params_path}")
        return 1

    params = json.loads(params_path.read_text())
    renders = params.get("renders") or []
    if not renders:
        record(False, "params.renders", "empty")

    for item in renders:
        png = resolve(ev, item.get("png") or "")
        log = resolve(ev, item.get("log") or "")
        sha_name = item.get("sha256") or (png.name + ".sha256")
        sha_path = resolve(ev, sha_name)
        name = png.name or "(missing png field)"

        if not png.is_file():
            record(False, f"render exists {name}", str(png))
            continue
        ok, stats = image_ok(png, expect_size=(1920, 1080))
        record(ok, f"render 1920x1080 non-blank {name}", json.dumps(stats, ensure_ascii=False))

        if not sha_path.is_file():
            record(False, f"sha256 file {sha_path.name}", "missing")
        else:
            declared = read_declared_sha(sha_path)
            actual = sha256_file(png)
            record(
                bool(declared) and declared == actual,
                f"sha256 matches {name}",
                f"declared={declared} actual={actual}",
            )

        if not log.is_file():
            record(False, f"render log {log.name}", "missing")
        else:
            size = log.stat().st_size
            record(size > 0, f"render log non-empty {log.name}", f"bytes={size}")

    # r2+: every render must declare official content and a quantitative diff vs gold.
    if params.get("require_official_content"):
        for item in renders:
            record(bool(item.get("official_content_manifest")), f"render uses official content {item.get('png')}",
                   str(item.get("official_content_manifest")))
        diff = params.get("diff_vs_gold") or {}
        record(all(k in diff for k in ("mae", "ssim")), "quantitative diff vs gold (mae, ssim)", json.dumps(diff)[:200])

    comp = params.get("comparison")
    if not comp:
        record(False, "comparison", "params.comparison missing")
    else:
        cpath = resolve(ev, comp)
        if not cpath.is_file():
            record(False, "comparison exists", str(cpath))
        else:
            ok, stats = image_ok(cpath, expect_size=None)
            record(ok, f"comparison exists non-blank {cpath.name}", json.dumps(stats, ensure_ascii=False))

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
