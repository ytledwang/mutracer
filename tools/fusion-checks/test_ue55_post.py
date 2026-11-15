#!/usr/bin/env python3
"""Unit checks for the opt-in UE 5.5 post approximation (ue_filmic.ue55_post)."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dual-track", "blender"))
from ue_filmic import ue55_post, film_tonemap_ap1, SRGB_2_AP1, AP1_2_SRGB, ue55_exposure_scale

ident = AP1_2_SRGB @ SRGB_2_AP1
assert np.allclose(ident, np.eye(3), atol=2e-3), ident
assert np.allclose(SRGB_2_AP1 @ np.ones(3), np.ones(3), atol=3e-3), "white must map to white"
assert abs(ue55_exposure_scale(0.8) - 2 ** 0.8 / 1.2) < 1e-9
x = np.geomspace(1e-4, 64, 400).astype(np.float32)
g = np.stack([x, x, x], 1)
t = film_tonemap_ap1(g)[:, 1]
assert np.all(np.diff(t) >= -1e-5), "filmic must be monotone"
assert t[-1] <= 1.04 + 1e-4, "white clip 0.04 bounds the shoulder"
assert 0.05 < float(film_tonemap_ap1(np.array([[0.18] * 3], np.float32))[0, 1]) < 0.25, "mid grey near 0.18"
post = {"exposure": 0.8, "gamma": 0.9, "contrast": 1.2, "saturation": 0.8, "temperature": 6500, "gain": 1, "offset": 0}
d = ue55_post(g, np.ones(len(x)), post, background_linear=10.0)
assert np.all(np.diff(d[:, 1]) >= -1e-5), "full chain monotone on neutrals"
assert np.all(np.abs(d[:, 0] - d[:, 2]) < 2e-3), "neutrals stay neutral"
bg = ue55_post(np.zeros((1, 3), np.float32), np.zeros(1), post, background_linear=10.0)
assert bg.min() > 0.995, f"white backdrop x10 must tonemap to white, got {bg}"
vals = [255 * float(ue55_post(np.array([[v] * 3], np.float32), np.ones(1), post)[0, 1]) for v in (0.18, 1.0)]
print("test_ue55_post OK; lin0.18->%.1f lin1.0->%.1f bg->%.1f (/255)" % (vals[0], vals[1], 255 * float(bg[0, 0])))
