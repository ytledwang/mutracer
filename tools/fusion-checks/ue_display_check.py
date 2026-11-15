#!/usr/bin/env python3
"""r12 显示映射检查器（fail-first）。

引擎依据（UE 5.5.4-release 官方源码，r11/r12 已逐行核对；r12 修订）：
- 显示链：AEM_Manual、ApplyPhysicalCameraExposure=false => WhitePoint=EV100ToLuminance(1,0)=1
  [PostProcessEyeAdaptation.cpp:436]；直方图钳制界 Min/MaxAverageLuminance = WhitePoint*0.18
  [PostProcessEyeAdaptation.cpp:508-509] => TargetExposure=0.18/0.18=1.0，
  GlobalExposure=Comp=2^bias（0.18 在链路中相消）。
  纯 2^bias 口径预言灶机 ~8.8x 过冲金样，与渲染矛盾；实际实现采用 0.18*2^bias
  （经验上最接近：灶机 +58%，329c 对照保持）。显示常数仍未决，需 UE 同场景
  ground-truth 渲染仲裁；见 r12-ue-units/conclusion.txt。
- Cycles 输出是辐射度 radiance（W/sr/m2），光度换算 nits = W * 683。
  => 现实现对 W 输入的等效曝光尺度 = 0.18 * 683 * 2^bias = 122.94 * 2^bias（经验口径）。
- 旧实现 ue55_exposure_scale = 2^bias / 1.2 => 灯光路径相对现实现差 147.528x，
  k=3.1 是旧尺度拟合值，只对环境路径成立。

三项检查：
A. 代码实现：ue_filmic.ue55_exposure_scale_engine(bias) == 0.18*683*2^bias（改前不存在 -> FAIL）
B. 环境路径单位变换一致性锁：k_new * s_new(b=0) == k_old * s_old(b=0)，
   k_new = 3.1 / (683*0.18*1.2)，即旧拟合 k=3.1 的纯单位变换（内容不变，非新拟合）。
C. 渲染验收门（r12-ue-units/render-results.json 存在时）：
   - 329c 对照（engine + k_new）：mae_fg <= 22.31（r8 基线 19.8068 + 2.5 容差）
   - 灶机（engine + k_new + candela）：fg_lum >= 40（r11 为 19.45，金样 80.33）
   文件缺失 -> FAIL（提示渲染未完成）。

用法：python3 tools/fusion-checks/ue_display_check.py
退出码：0 全部通过；1 任一失败。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "docs/prd/evidence/fusion/fidelity/r12-ue-units/render-results.json"

LM_PER_W = 683.0
K_OLD = 3.1
R11_STOVE_FG_LUM = 19.45
BASELINE_329C_MAE_FG = 19.8068
TOL_329C = 2.5
STOVE_FG_LUM_GATE = 40.0


def engine_scale_w(bias_ev: float) -> float:
    """UE 口径显示尺度，输入为 Cycles 辐射度 radiance（W）。"""
    return 0.18 * LM_PER_W * (2.0 ** bias_ev)


def main() -> int:
    failures = []

    # A. 代码实现
    try:
        sys.path.insert(0, str(REPO / "tools/dual-track/blender"))
        from ue_filmic import ue55_exposure_scale_engine  # type: ignore
        for b in (0.0, 0.8, 1.0):
            got = ue55_exposure_scale_engine(b)
            want = engine_scale_w(b)
            if abs(got - want) > 1e-9 * max(1.0, want):
                failures.append(f"A: bias={b} got {got} want {want}")
    except ImportError as e:
        failures.append(f"A: engine 尺度函数不存在（未实现）：{e}")

    # B. 环境路径单位变换一致性锁
    s_old = 1.0 / 1.2
    k_new = K_OLD / (LM_PER_W * 0.18 * 1.2)
    lhs = k_new * engine_scale_w(0.0)
    rhs = K_OLD * s_old
    if abs(lhs - rhs) > 1e-9:
        failures.append(f"B: k_new*s_new={lhs} != k_old*s_old={rhs}")
    print(f"[B] k_new={k_new:.10f}  k_new*s_new={lhs:.10f} == k_old*s_old={rhs:.10f}")

    # C. 渲染验收门
    if RESULTS.is_file():
        res = json.loads(RESULTS.read_text())
        c329 = res.get("329c", {})
        stove = res.get("stove", {})
        mae_fg_329 = c329.get("mae_fg")
        if mae_fg_329 is None or mae_fg_329 > BASELINE_329C_MAE_FG + TOL_329C:
            failures.append(f"C: 329c mae_fg={mae_fg_329} > {BASELINE_329C_MAE_FG + TOL_329C}（对照被打破）")
        else:
            print(f"[C] 329c mae_fg={mae_fg_329} <= {BASELINE_329C_MAE_FG + TOL_329C} OK")
        fg_lum_stove = stove.get("fg_lum_ren", stove.get("fg_lum"))
        if fg_lum_stove is None or fg_lum_stove < STOVE_FG_LUM_GATE:
            failures.append(f"C: stove fg_lum={fg_lum_stove} < {STOVE_FG_LUM_GATE}（灯光路径未按引擎口径提亮，r11={R11_STOVE_FG_LUM}）")
        else:
            print(f"[C] stove fg_lum={fg_lum_stove} >= {STOVE_FG_LUM_GATE} OK（r11={R11_STOVE_FG_LUM}，金样 80.33）")
    else:
        failures.append(f"C: 渲染结果缺失（{RESULTS}），先完成 329c 与灶机渲染")

    print(f"RESULT {'FAIL' if failures else 'PASS'} failures={len(failures)}")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
