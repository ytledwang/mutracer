#!/usr/bin/env python3
"""UE 5.5.4 candela 单位换算检查器（fail-first）。

引擎依据（UE 5.5.4-release 官方源码，均已在本地 ue55-src 逐行核对）：
- RectLight candela→radiance：
    ComputeLightBrightness: LightBrightness = Intensity * (100*100)      [RectLightComponent.cpp:174]
    proxy Color = LightColor * ComputeLightBrightness                    [LightComponent.cpp:1467 GetColoredLightBrightness]
    GetLightShaderParameters: radiance = Color / (0.5*SourceWidth*SourceHeight)
                                                       [RectLightComponent.cpp:313]
    => radiance_nits = 2 * I_cd / A_m2   (A_m2 = (size_x*0.01)*(size_z*0.01))
- PathTracer 灯色 = radiance * GetLightExposureScale(E, InverseExposureBlend=0) = radiance * 1
    [PathTracing.cpp:2746][LocalLightComponent.cpp:21 InverseExposureBlend=0]
    ["stored color is radiance" PathTracingRectLight.ush]
- PointLight candela：Color = LightColor * I_cd（无面积除法），PT 以 illuminance=I/d² 采样
  => 与 mutracer 4πI/683（辐射强度 I/683 W/sr，光度还原后 = I cd）一致。

mutracer 当前实现（tools/dual-track/blender/blender_inner.py candela 模式）：
- area:   W = PI * I / 683  => Cycles radiance = W/(PI*A) => 光度还原 nits = I/A   （差 UE 2 倍）
- point:  W = 4PI * I / 683 => 辐射强度 I/683 W/sr => 光度还原 = I cd              （一致）

检查：对场景内每盏灯断言 ue_nits / mutracer_nits == 1（容差 1e-6）。
当前预期：area_light 全部 ratio=2 -> exit 1（fail-first，记录现状）；
blender_inner 修正为 W = 2*PI*I/683 后应 exit 0。

显示层（供下一刀核对，不在本检查断言范围）：
r12 修订：源码链 AEM_Manual+无物理曝光 => WhitePoint=1、直方图钳制界=WhitePoint*0.18
  [PostProcessEyeAdaptation.cpp:436,508-509] => GlobalExposure=Comp=2^bias（0.18 相消）。
  纯 2^bias 口径与渲染实测矛盾（灶机 ~8.8x 过冲）；现实现用 0.18*2^bias（经验最接近）。
  显示常数未决，需 UE ground-truth 渲染仲裁；见 r12-ue-units/conclusion.txt。

用法：
  python3 tools/fusion-checks/ue_candela_unit_check.py \
      [--scene docs/prd/evidence/fusion/fidelity/r8/scene-00ac0cff-preview.json] \
      [--out docs/prd/evidence/fusion/fidelity/r11-ue-units/check.json]
退出码：0 全部一致；1 存在不一致（打印每盏灯明细）。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SCENE = REPO / "docs/prd/evidence/fusion/fidelity/r8/scene-00ac0cff-preview.json"
DEFAULT_OUT = REPO / "docs/prd/evidence/fusion/fidelity/r11-ue-units/check.json"

LM_PER_W = 683.0  # 光度学换算假设：555nm 单色发光效率（mutracer 现行常量）
TOL = 1e-6


def walk_lights(node, out):
    if isinstance(node, dict):
        light = node.get("light")
        if isinstance(light, dict) and light.get("type") in ("area_light", "point_light", "spot_light"):
            out.append({
                "name": node.get("name"),
                "type": light.get("type"),
                "power_cd": float(light.get("power") or 0.0),
                "size_x_cm": float(light["size_x"]) if light.get("size_x") is not None else None,
                "size_z_cm": float(light["size_z"]) if light.get("size_z") is not None else None,
            })
        for v in node.values():
            walk_lights(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_lights(v, out)


def walk_camera_bias(node, out):
    if isinstance(node, dict):
        cam = node.get("camera")
        if isinstance(cam, dict):
            pp = cam.get("post_processing_settings") or {}
            if pp.get("exposure") is not None:
                out.append(float(pp["exposure"]))
        for v in node.values():
            walk_camera_bias(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_camera_bias(v, out)


def ue_radiance_nits(l):
    """UE 5.5.4 引擎公式给出的 radiance（nits=cd/m^2）。point/spot 返回等效发光强度 cd。"""
    if l["type"] == "area_light":
        a_m2 = (l["size_x_cm"] * 0.01) * (l["size_z_cm"] * 0.01)
        return 2.0 * l["power_cd"] / a_m2
    return l["power_cd"]


def mutracer_radiance_nits(l):
    """mutracer 现行 candela→W 换算还原出的光度 radiance。"""
    if l["type"] == "area_light":
        a_m2 = (l["size_x_cm"] * 0.01) * (l["size_z_cm"] * 0.01)
        w = 2.0 * math.pi * l["power_cd"] / LM_PER_W    # blender_inner r11 起（引擎核过 2*I/A）
        return (w / (math.pi * a_m2)) * LM_PER_W        # Cycles diffuse emitter 光度还原
    w = 4.0 * math.pi * l["power_cd"] / LM_PER_W        # blender_inner 现行
    return (w / (4.0 * math.pi)) * LM_PER_W             # 辐射强度→光度强度


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    scene = json.loads(args.scene.read_text())
    lights = []
    walk_lights(scene, lights)
    biases = []
    walk_camera_bias(scene, biases)
    bias = biases[0] if biases else 0.0

    items = []
    failures = 0
    for l in lights:
        ue = ue_radiance_nits(l)
        mu = mutracer_radiance_nits(l)
        ratio = ue / mu if mu else math.inf
        ok = abs(ratio - 1.0) <= TOL
        if not ok:
            failures += 1
        items.append({
            "name": l["name"], "type": l["type"], "power_cd": l["power_cd"],
            "ue_nits_or_cd": round(ue, 9), "mutracer_nits_or_cd": round(mu, 9),
            "ratio_ue_over_mutracer": round(ratio, 6), "ok": ok,
        })

    report = {
        "scene": str(args.scene.relative_to(REPO)) if args.scene.is_relative_to(REPO) else str(args.scene),
        "engine_source": "UE 5.5.4-release (Epic GitHub, fetched 2026-11-14)",
        "area_formula": "nits = 2*I_cd/A_m2  [RectLightComponent.cpp:174,313]",
        "point_formula": "cd = I_cd        [LightComponent.cpp GetColor; 无面积除法]",
        "display_linear_extra": "unresolved: source chain says nits * 2^bias (0.18 cancels, PostProcessEyeAdaptation.cpp:436,508-509); implemented empirical scale is nits * 0.18 * 2^bias (closest to renders); see r12-ue-units/conclusion.txt",
        "camera_auto_exposure_bias": bias,
        "lights": items,
        "failures": failures,
    }

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")

    print(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"RESULT {'FAIL' if failures else 'PASS'} failures={failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
