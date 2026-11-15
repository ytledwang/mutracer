#!/usr/bin/env python3
"""Compose a labeled side-by-side fidelity comparison. Not invoked by the checker."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size, index=0)
        except Exception:
            continue
    return ImageFont.load_default()


def fit(im: Image.Image, box: tuple[int, int]) -> Image.Image:
    im = im.convert("RGB")
    fitted = im.copy()
    fitted.thumbnail(box, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", box, (20, 20, 20))
    x = (box[0] - fitted.width) // 2
    y = (box[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--panel", action="append", nargs=2, metavar=("PATH", "LABEL"), required=True)
    parser.add_argument("--title", default="Fidelity comparison")
    args = parser.parse_args()

    panels = []
    for path, label in args.panel:
        im = Image.open(path)
        panels.append((Path(path), im, label.replace("\\n", "\n")))

    panel_w, panel_h = 960, 540
    header_h = 56
    caption_h = 132
    gap = 16
    margin = 24
    n = len(panels)
    width = margin * 2 + n * panel_w + (n - 1) * gap
    height = margin * 2 + header_h + panel_h + caption_h
    canvas = Image.new("RGB", (width, height), (18, 18, 20))
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(28)
    caption_font = load_font(16)
    small_font = load_font(14)

    draw.text((margin, margin + 8), args.title, fill=(240, 240, 230), font=title_font)

    for i, (path, im, label) in enumerate(panels):
        x = margin + i * (panel_w + gap)
        y = margin + header_h
        fitted = fit(im, (panel_w, panel_h))
        canvas.paste(fitted, (x, y))
        draw.rectangle([x, y, x + panel_w - 1, y + panel_h - 1], outline=(60, 60, 64))
        cy = y + panel_h + 8
        for line in label.split("\n"):
            for wrapped in wrap(draw, line, caption_font, panel_w - 8):
                draw.text((x + 4, cy), wrapped, fill=(220, 220, 210), font=caption_font)
                cy += 20
        draw.text((x + 4, y + panel_h + caption_h - 22), path.name, fill=(140, 140, 140), font=small_font)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "PNG")
    digest = sha256_file(out)
    (Path(str(out) + ".sha256")).write_text(f"{digest}  {out.name}\n")
    print(json.dumps({"out": str(out), "sha256": digest, "size": canvas.size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
