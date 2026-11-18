#!/usr/bin/env python3
"""r14 定版候选检查（fail-first）：冻结参数 + 多产品对标。

三关：
 P 参数一致：冻结值 == ue_filmic.ENGINE_DISPLAY_GRAY；k_new*s_new == 3.1/1.2；
   每个产品的渲染所用 gray/skylight 必须等于冻结值（旧参数渲的图判失败）。
 L 亮度：|前景亮度 - 金样前景亮度| <= fg_lum_abs_diff_max。
 S 结构：SSIM >= ssim_min。
用法：python3 tools/fusion-checks/ue_display_freeze_check.py [out.json]
退出码：0 全过；1 有失败。
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FID = REPO / "docs/prd/evidence/fusion/fidelity"
MAN = FID / "r14-freeze/manifest.json"


def main() -> int:
    sys.path.insert(0, str(REPO / "tools/fusion-checks"))
    sys.path.insert(0, str(REPO / "tools/dual-track/blender"))
    from fidelity_r4_analyze import LUM, fg_mask, load, ssim_lum
    from ue_filmic import ENGINE_DISPLAY_GRAY, ue55_exposure_scale, ue55_exposure_scale_engine

    man = json.loads(MAN.read_text())
    fz, th = man["frozen"], man["thresholds"]
    fails: list[str] = []
    rows = {}

    if abs(ENGINE_DISPLAY_GRAY - fz["gray"]) > 1e-9:
        fails.append(f"P: ENGINE_DISPLAY_GRAY {ENGINE_DISPLAY_GRAY} != frozen {fz['gray']}")
    if abs(ue55_exposure_scale(0.0) - 1 / 1.2) > 1e-12:
        fails.append("P: legacy exposure scale moved")
    k = 3.1 / (683.0 * fz["gray"] * 1.2)
    if abs(k - fz["k_new"]) > 1e-6:
        fails.append(f"P: k_new {k:.10f} != frozen {fz['k_new']}")
    if abs(k * ue55_exposure_scale_engine(0.0) - 3.1 / 1.2) > 1e-6:
        fails.append("P: env product k_new*s_new != 3.1/1.2")

    for pid, p in man["products"].items():
        r, g = FID / p["render"], FID / p["gold"]
        if abs(p["gray"] - fz["gray"]) > 1e-9 or abs(p["skylight_scale"] - fz["k_new"]) > 1e-6:
            fails.append(f"P[{pid}]: 渲染用参数过期 gray={p['gray']} sky={p['skylight_scale']}")
        if not (r.is_file() and g.is_file()):
            fails.append(f"[{pid}]: 文件缺失 render={r.is_file()} gold={g.is_file()}")
            continue
        gold, ren = load(str(g)), load(str(r))
        fg = fg_mask(gold)
        lr, lg = float((ren[fg] @ LUM).mean()), float((gold[fg] @ LUM).mean())
        ss = ssim_lum(gold, ren)
        rows[pid] = {"fg_lum": round(lr, 2), "gold_fg_lum": round(lg, 2), "d_lum": round(lr - lg, 2), "ssim": round(ss, 4)}
        print(f"[{pid}] {p['kind']}: fg {lr:.1f} vs gold {lg:.1f} (d={lr-lg:+.1f}) ssim={ss:.3f}")
        if abs(lr - lg) > th["fg_lum_abs_diff_max"]:
            fails.append(f"L[{pid}]: |d_lum|={abs(lr-lg):.1f} > {th['fg_lum_abs_diff_max']}")
        if ss < th["ssim_min"]:
            fails.append(f"S[{pid}]: ssim={ss:.3f} < {th['ssim_min']}")

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps({"rows": rows, "fails": fails}, ensure_ascii=False, indent=1))
    print(f"RESULT {'FAIL' if fails else 'PASS'} failures={len(fails)}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
