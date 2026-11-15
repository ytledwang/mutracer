#!/usr/bin/env python3
"""Offline env-strength calibration on a no-light linear render: with no stage lights and
sky-scale 0, all lighting scales linearly with the world strength, so scaling the linear
image by s == rendering with hdri-reflection*s. Uses ue_filmic.ue_post + r4 metrics.
Usage: fidelity_r5_sweep.py LINEAR.npy SCENE.json CAMERA_ID OUT.json"""
import json, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dual-track", "blender"))
sys.path.insert(0, os.path.dirname(__file__))
from ue_filmic import ue_post
from fidelity_r4_analyze import load, fg_mask, ssim_lum, LUM
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
gold = load(os.path.join(ROOT, "docs/prd/evidence/fusion/fidelity/r2/reference-fridge-ref-front-329c-1920.png"))
fg = fg_mask(gold)
lin = np.load(sys.argv[1]).astype(np.float32)
s = json.load(open(sys.argv[2])); s = s.get("scene_json", s)
post = s["cameras"][sys.argv[3]]["camera"]["post_processing_settings"]
h, w = lin.shape[:2]
res = []
for scale in np.exp(np.linspace(np.log(0.03), np.log(1.5), 40)):
    disp = ue_post(lin[..., :3].reshape(-1, 3), lin[..., 3].ravel(), post, exposure_ev=float(post.get("exposure", 0)), scale=scale)
    img = np.round(np.clip(disp, 0, 1) * 255).reshape(h, w, 3)
    d = np.abs(gold - img)
    res.append({"scale": round(float(scale), 5), "mae": round(float(d.mean()), 4), "mae_fg": round(float(d[fg].mean()), 4),
                "d_lum_fg": round(float((img[fg] @ LUM - gold[fg] @ LUM).mean()), 3)})
best = min(res, key=lambda r: r["mae_fg"])
disp = ue_post(lin[..., :3].reshape(-1, 3), lin[..., 3].ravel(), post, exposure_ev=float(post.get("exposure", 0)), scale=best["scale"])
img = np.round(np.clip(disp, 0, 1) * 255).reshape(h, w, 3)
best["ssim"] = round(ssim_lum(gold, img), 6)
json.dump({"sweep": res, "best_by_mae_fg": best}, open(sys.argv[4], "w"), indent=1)
for r in res[::3]: print(r)
print("BEST", best)
