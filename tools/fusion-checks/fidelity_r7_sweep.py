#!/usr/bin/env python3
"""Offline r7 env-weight sweep. With no lights, the linear radiance is
L = C + a*(A - C) + b*(B - C), A = 4.exr SkyLight basis, B = white-sky basis,
C = no-env (emissive only). Each combination goes through ue_filmic.ue55_post
(white backdrop x hdri_brightness via alpha) and the r4 metrics vs gold.
usage: fidelity_r7_sweep.py OUT.json A.npy [B.npy C.npy] [--a LIST] [--b LIST]"""
import json, sys, os, argparse
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dual-track", "blender"))
sys.path.insert(0, os.path.dirname(__file__))
from ue_filmic import ue55_post
from fidelity_r4_analyze import load, fg_mask, ssim_lum, LUM
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REGIONS = {"interior_cavity": (735, 105, 1045, 345), "crisper_bins": (715, 360, 1060, 545), "drawers": (685, 595, 1092, 985),
           "door_left_inner": (600, 60, 700, 550), "door_right_inner": (1075, 60, 1185, 550)}
p = argparse.ArgumentParser(); p.add_argument("out"); p.add_argument("A"); p.add_argument("B", nargs="?"); p.add_argument("C", nargs="?")
p.add_argument("--a", default="0.25,0.35,0.5,0.7,1.0,1.4,2.0"); p.add_argument("--b", default="0"); p.add_argument("--save-best")
args = p.parse_args()
gold_full = Image.open(os.path.join(ROOT, "docs/prd/evidence/fusion/fidelity/r2/reference-fridge-ref-front-329c-1920.png")).convert("RGB")
A = np.load(args.A).astype(np.float64); h, w = A.shape[:2]
gold = np.asarray(gold_full.resize((w, h), Image.LANCZOS) if (w, h) != gold_full.size else gold_full, np.float64)
fg = fg_mask(gold)
B = np.load(args.B).astype(np.float64) if args.B else None; C = np.load(args.C).astype(np.float64) if args.C else None
s = json.load(open(os.path.join(ROOT, "docs/prd/evidence/fusion/fidelity/r5/scene-gold329c-preview.json"))); s = s.get("scene_json", s)
post = s["cameras"]["858db55c-a0ca-4d4d-8a80-0cd2e2b0a3b1"]["camera"]["post_processing_settings"] if "858db55c-a0ca-4d4d-8a80-0cd2e2b0a3b1" in s["cameras"] else \
    [c for k, c in s["cameras"].items() if k.startswith("858db55c")][0]["camera"]["post_processing_settings"]
env = [e for e in s["environments"].values()][0] if isinstance(s.get("environments"), dict) else {}
bright = 10.0
def compose(a, b):
    rgb = A[..., :3] * a; al = A[..., 3]
    if C is not None: rgb = rgb + C[..., :3] * (1 - a - b)
    if B is not None: rgb = rgb + B[..., :3] * b
    return np.round(ue55_post(rgb.reshape(-1, 3), al.ravel(), post, background_linear=bright) * 255).reshape(h, w, 3)
res = []
for a in map(float, args.a.split(",")):
    for b in map(float, args.b.split(",")):
        img = compose(a, b); d = np.abs(gold - img)
        r = {"a": a, "b": b, "mae": round(float(d.mean()), 4), "mae_fg": round(float(d[fg].mean()), 4),
             "d_lum_fg": round(float((img[fg] @ LUM - gold[fg] @ LUM).mean()), 3)}
        sx, sy = w / 1920, h / 1080
        for n, (x0, y0, x1, y1) in REGIONS.items():
            sl = (slice(int(y0 * sy), int(y1 * sy)), slice(int(x0 * sx), int(x1 * sx)))
            r[n] = [round(float(np.median(img[sl] @ LUM)), 1), round(float(np.median(gold[sl] @ LUM)), 1)]
        res.append(r)
best = min(res, key=lambda r: r["mae_fg"]); img = compose(best["a"], best["b"]); best["ssim"] = round(ssim_lum(gold, img), 6)
if args.save_best: Image.fromarray(img.astype(np.uint8)).save(args.save_best)
json.dump({"sweep": res, "best_by_mae_fg": best}, open(args.out, "w"), indent=1)
for r in res: print({k: r[k] for k in ("a", "b", "mae", "mae_fg", "d_lum_fg", "door_left_inner", "door_right_inner", "drawers")})
print("BEST", best)
