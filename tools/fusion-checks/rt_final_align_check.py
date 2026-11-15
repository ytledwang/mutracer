#!/usr/bin/env python3
"""Realtime-vs-final alignment metric check (can fail).

usage: rt_final_align_check.py REALTIME.png FINAL.png [--out metrics.json] [--side side.png]

The realtime canvas is resized to the final's size. The fridge region is the
final's foreground mask (pixels whose luminance differs from the final's border
background by > 12). Over that mask we compare mean luminance and mean RGB.
Tolerances (8-bit sRGB):
  |Δ mean lum|        <= 10
  max |Δ mean R/G/B|  <= 12
  background |Δ lum|  <= 12   (border ring)
  mask IoU            >= 0.80 (same framing / camera)
Exit 0 only if all pass.
"""
from __future__ import annotations
import json, sys, argparse
import numpy as np
from PIL import Image

TOL = {"lum": 10.0, "rgb": 12.0, "bg": 12.0, "iou": 0.80}


def lum(a):
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def border_bg(a, frac=0.03):
    h, w = a.shape[:2]
    b = max(2, int(min(h, w) * frac))
    ring = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    return np.median(ring, axis=0)


def fg_mask(a):
    bg = border_bg(a)
    return np.abs(lum(a) - lum(bg[None, None, :])) > 12.0, bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("realtime"); ap.add_argument("final")
    ap.add_argument("--out"); ap.add_argument("--side")
    a = ap.parse_args()
    fin = Image.open(a.final).convert("RGB")
    rt = Image.open(a.realtime).convert("RGB").resize(fin.size, Image.LANCZOS)
    F = np.asarray(fin, dtype=np.float32); R = np.asarray(rt, dtype=np.float32)
    mF, bgF = fg_mask(F); mR, bgR = fg_mask(R)
    inter = float((mF & mR).sum()); union = float((mF | mR).sum()) or 1.0
    iou = inter / union
    if mF.sum() < 1000:
        print("FAIL  final foreground mask too small"); return 1
    mf = F[mF].mean(axis=0); mr = R[mF].mean(axis=0)
    d = {
        "realtime": a.realtime, "final": a.final, "size": list(fin.size),
        "final_rgb": mf.round(2).tolist(), "realtime_rgb": mr.round(2).tolist(),
        "final_lum": round(float(lum(mf[None, None, :])[0, 0]), 2),
        "realtime_lum": round(float(lum(mr[None, None, :])[0, 0]), 2),
        "bg_final_rgb": bgF.round(1).tolist(), "bg_realtime_rgb": bgR.round(1).tolist(),
        "mask_iou": round(iou, 4), "mask_px": int(mF.sum()),
        "mae_fg": round(float(np.abs(F[mF] - R[mF]).mean()), 2),
        "tolerance": TOL,
    }
    d["d_lum"] = round(d["realtime_lum"] - d["final_lum"], 2)
    d["d_rgb"] = (mr - mf).round(2).tolist()
    d["d_bg_lum"] = round(float(lum(bgR[None, None, :])[0, 0] - lum(bgF[None, None, :])[0, 0]), 2)
    checks = [
        ("fridge mean luminance |Δ| <= %.0f" % TOL["lum"], abs(d["d_lum"]) <= TOL["lum"], d["d_lum"]),
        ("fridge mean RGB max|Δ| <= %.0f" % TOL["rgb"], max(abs(x) for x in d["d_rgb"]) <= TOL["rgb"], d["d_rgb"]),
        ("background luminance |Δ| <= %.0f" % TOL["bg"], abs(d["d_bg_lum"]) <= TOL["bg"], d["d_bg_lum"]),
        ("fridge mask IoU >= %.2f" % TOL["iou"], iou >= TOL["iou"], d["mask_iou"]),
    ]
    fail = 0
    for name, ok, v in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  value={v}")
        fail += 0 if ok else 1
    d["checks"] = [{"name": n, "pass": bool(o), "value": v} for n, o, v in checks]
    d["pass"] = fail == 0
    print(json.dumps({k: d[k] for k in ("final_lum", "realtime_lum", "final_rgb", "realtime_rgb", "mask_iou", "mae_fg")}))
    if a.out:
        json.dump(d, open(a.out, "w"), indent=2, ensure_ascii=False)
    if a.side:
        W, H = 960, 540
        canvas = Image.new("RGB", (W * 2 + 30, H + 60), "white")
        canvas.paste(rt.resize((W, H)), (10, 50)); canvas.paste(fin.resize((W, H)), (W + 20, 50))
        try:
            from PIL import ImageDraw, ImageFont
            dr = ImageDraw.Draw(canvas)
            font = None
            for fp in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"):
                try:
                    font = ImageFont.truetype(fp, 22); break
                except Exception:
                    pass
            dr.text((10, 12), f"实时查看 realtime  lum={d['realtime_lum']}", fill="black", font=font)
            dr.text((W + 20, 12), f"提交渲染 final (Standard)  lum={d['final_lum']}  IoU={d['mask_iou']}", fill="black", font=font)
        except Exception:
            pass
        canvas.save(a.side)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
