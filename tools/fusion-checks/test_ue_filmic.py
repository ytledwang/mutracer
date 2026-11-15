#!/usr/bin/env python3
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dual-track", "blender"))
from ue_filmic import ue_post, aces_fitted
post = {"exposure": 0.8, "gamma": 0.9, "contrast": 1.2, "saturation": 0.8, "temperature": 6500, "gain": 1, "offset": 0}
x = np.linspace(0, 8, 2000, dtype=np.float32)
g = np.stack([x, x, x], 1)
y = ue_post(g, np.ones(len(x)), post)[:, 1]
assert np.all(np.diff(y) >= -1e-6), "not monotone"
assert abs(aces_fitted(np.float32(1.0)) - 0.8038) < 1e-3, "ACES fit anchor"
assert np.all(ue_post(g, np.zeros(len(x)), post) == 1.0), "backdrop must stay white"
assert ue_post(np.array([[0.18, 0.18, 0.18]], np.float32), np.ones(1), {"contrast": 2.0})[0, 0] == ue_post(np.array([[0.18, 0.18, 0.18]], np.float32), np.ones(1), {})[0, 0], "contrast pivot 0.18"
print("test_ue_filmic OK; white(1.0 lin, gold post)=%.1f/255" % (255 * ue_post(np.ones((1, 3), np.float32), np.ones(1), post)[0, 0]))
