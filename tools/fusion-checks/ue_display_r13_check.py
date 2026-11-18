#!/usr/bin/env python3
"""r13 灯路系数检查（fail-first）。

2026-11-15 同场景 UE 出图把灶机前景钉在 83.73，金样 80.33。
r12 engine 档是 126.82。0.114 只到前景 101.48，系数改为插值 0.06779987。
环境路径仍锁 k_new * s_new == 3.1/1.2。legacy 曝光尺度不变。
纯 2^bias 不采用。

用法：python3 tools/fusion-checks/ue_display_r13_check.py
退出码：0 通过；1 失败。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs/prd/evidence/fusion/fidelity/r13-ue-gt/render-00ac0cff-front-r13.png"
UE = REPO / "docs/prd/evidence/fusion/fidelity/r13-ue-gt/ue-00ac0cff-front-1920.png"
GOLD = REPO / "docs/prd/evidence/fusion/fidelity/r8/golds/00ac0cff-front-1920.png"
METRICS = REPO / "docs/prd/evidence/fusion/fidelity/r13-ue-gt/metrics.json"

LM_PER_W = 683.0
K_OLD = 3.1
R12_FG = 126.8227
UE_FG = 83.73
# Interpolated from (0.18 -> 126.82) and (0.11401541 -> 101.48) toward UE 83.73.
GRAY = 0.06779987
FG_LO = 72.0
FG_HI = 88.0


def main() -> int:
    sys.path.insert(0, str(REPO / "tools/fusion-checks"))
    sys.path.insert(0, str(REPO / "tools/dual-track/blender"))
    from fidelity_r4_analyze import LUM, fg_mask, load, ssim_lum
    from ue_filmic import ENGINE_DISPLAY_GRAY, ue55_exposure_scale, ue55_exposure_scale_engine

    failures = []
    if abs(ENGINE_DISPLAY_GRAY - GRAY) > 1e-9:
        failures.append(f"A: ENGINE_DISPLAY_GRAY {ENGINE_DISPLAY_GRAY} != {GRAY}")
    for b in (0.0, 1.0):
        want = GRAY * LM_PER_W * (2.0 ** b)
        got = ue55_exposure_scale_engine(b)
        if abs(got - want) > 1e-6:
            failures.append(f"A: bias={b} got {got} want {want}")
    if abs(ue55_exposure_scale(0.0) - (1.0 / 1.2)) > 1e-12:
        failures.append("A: legacy exposure scale moved")
    k_new = K_OLD / (LM_PER_W * GRAY * 1.2)
    lhs = k_new * ue55_exposure_scale_engine(0.0)
    rhs = K_OLD / 1.2
    if abs(lhs - rhs) > 1e-6:
        failures.append(f"B: k_new*s_new={lhs} != {rhs}")
    print(f"[B] gray={GRAY:.8f} k_new={k_new:.10f}")

    if not OUT.is_file() or not UE.is_file():
        failures.append(f"C: 渲染或 UE 图缺失 out={OUT.is_file()} ue={UE.is_file()}")
    else:
        gold = load(str(GOLD))
        rend = load(str(OUT))
        ue = load(str(UE))
        fg = fg_mask(gold)
        fg_lum = float((rend[fg] @ LUM).mean())
        ue_lum = float((ue[fg] @ LUM).mean())
        d_ue = float(np.abs(rend - ue).mean())
        d_gold = float(np.abs(rend - gold)[fg].mean())
        print(f"[C] fg_lum={fg_lum:.2f} ue_fg={ue_lum:.2f} mae_ue={d_ue:.2f} mae_fg_gold={d_gold:.2f} ssim_ue={ssim_lum(ue, rend):.4f}")
        if not (FG_LO <= fg_lum <= FG_HI):
            failures.append(f"C: stove fg_lum={fg_lum:.2f} not in [{FG_LO},{FG_HI}]")
        if abs(fg_lum - ue_lum) >= abs(R12_FG - ue_lum):
            failures.append("C: 没有比 r12 更靠近 UE")
        METRICS.write_text(json.dumps({
            "fg_lum": round(fg_lum, 4),
            "ue_fg_lum": round(ue_lum, 4),
            "gold_fg_lum": round(float((gold[fg] @ LUM).mean()), 4),
            "mae_ue": round(d_ue, 4),
            "mae_fg_gold": round(d_gold, 4),
            "ssim_ue": round(ssim_lum(ue, rend), 6),
            "gray": GRAY,
            "k_new": k_new,
        }, indent=1))
    print(f"RESULT {'FAIL' if failures else 'PASS'} failures={len(failures)}")
    for item in failures:
        print("  -", item)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
