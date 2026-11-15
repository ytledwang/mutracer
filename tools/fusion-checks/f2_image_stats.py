#!/usr/bin/env python3
"""Canvas luminance / uniqueness / sha256 helpers for F2 acceptance.

Exit 1 when --expect-visible fails, or when --require-distinct hashes collide.
Never used to overwrite evidence; only reads paths given on the CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print('PIL is required', file=sys.stderr)
    sys.exit(2)

import numpy as np


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def canvas_stats(path: Path, margin: float = 0.0) -> dict:
    im = Image.open(path).convert('RGB')
    a = np.asarray(im, dtype=np.float32)
    h, w, _ = a.shape
    y0, y1 = int(h * margin), int(h * (1 - margin))
    x0, x1 = int(w * margin), int(w * (1 - margin))
    crop = a[y0:y1, x0:x1]
    lum = crop.mean(axis=2)
    # Background of the viewer viewport is near #15161a / #2a2b30.
    # Count a pixel "foreground" if it deviates from the median by enough,
    # or is brighter than a dark-ui floor.
    med = float(np.median(lum))
    fg = (np.abs(lum - med) > 18) | (lum > 55)
    unique = int(len(np.unique((lum / 8).astype(np.uint8))))
    # Inner crop: an HDRI sky/horizon is a vertical gradient (low row_std);
    # a fridge has horizontal structure.
    inner = lum[int(crop.shape[0]*0.1):int(crop.shape[0]*0.9), int(crop.shape[1]*0.1):int(crop.shape[1]*0.9)]
    row_std = float(inner.std(axis=1).mean()) if inner.size else 0.0
    col_std = float(inner.std(axis=0).mean()) if inner.size else 0.0
    return {
        'path': str(path),
        'width': w,
        'height': h,
        'mean': float(crop.mean()),
        'lum_mean': float(lum.mean()),
        'lum_std': float(lum.std()),
        'lum_median': med,
        'foreground_ratio': float(fg.mean()),
        'unique_lum_bins': unique,
        'row_std': row_std,
        'col_std': col_std,
        'sha256': sha256_file(path),
    }


def is_visible(stats: dict, min_fg: float = 0.03, min_std: float = 8.0, min_unique: int = 12, min_row_std: float = 10.0) -> bool:
    return (
        stats['foreground_ratio'] >= min_fg
        and stats['lum_std'] >= min_std
        and stats['unique_lum_bins'] >= min_unique
        and stats.get('row_std', 0) >= min_row_std
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('images', nargs='+', type=Path)
    p.add_argument('--expect-visible', action='store_true',
                   help='exit 1 if any image looks like a flat/black canvas')
    p.add_argument('--require-distinct', action='store_true',
                   help='exit 1 if any two given images share a sha256')
    p.add_argument('--json-out', type=Path)
    p.add_argument('--min-fg', type=float, default=0.03)
    p.add_argument('--min-std', type=float, default=8.0)
    args = p.parse_args(argv)

    report = []
    ok = True
    for img in args.images:
        if not img.is_file():
            report.append({'path': str(img), 'error': 'missing'})
            ok = False
            continue
        st = canvas_stats(img)
        st['visible'] = is_visible(st, min_fg=args.min_fg, min_std=args.min_std)
        if args.expect_visible and not st['visible']:
            ok = False
        report.append(st)

    if args.require_distinct:
        hashes = {}
        for st in report:
            digest = st.get('sha256')
            if not digest:
                continue
            hashes.setdefault(digest, []).append(st['path'])
        for digest, paths in hashes.items():
            if len(paths) > 1:
                ok = False
                report.append({'error': 'duplicate-sha256', 'sha256': digest, 'paths': paths})

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json_out:
        args.json_out.write_text(text + '\n')
    else:
        print(text)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
