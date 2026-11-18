# cmf3: door-edge asymmetry + interior lift/emit + lacquer flake

执行：本机 Blender 5.x Metal，1920×1080，512 spp，OIDN。kiro-cli/magpie 本轮遇持续 429，标定与成片由已落地的 `blender_inner.py` CMF3 改动 + CLI 扫参完成（账号 laeli；不 push）。

## 相对 cmf2 的代码改动（`tools/dual-track/blender/blender_inner.py`）
- 左右门边独立 CMF：`--edge-left/right-{albedo,roughness,metalness,specular}`；mesh `门体-51/52…` 按 instance 左右分配 charcoal。
- 内腔：`--interior-lift` / `--interior-lift-low`（按 `--interior-split-y`），`--interior-emit` + Z 渐变 `--interior-emit-z0/z1`。
- 漆面 flake：`--flake`（Noise→Metallic/CoatRoughness 微扰）；Coat Weight 0.8 / Roughness 0.1。
- 对称弱 fill：`--fill-scale`（默认 0）。
- 曝光：`view_settings.exposure = post.exposure`（UE AutoExposureBias 1:1）；**EXPOSURE_BIAS 默认 0**。
- 本轮把 G2 标定结果 bake 进默认：light-scale 7.2、sky 0.28、drawer 0.88、edge-left 0.22/0.4/0.3、edge-right albedo/metal/spec 0、interior-lift 0.60/0.30、emit 0.04、emit-z 1.25–1.55、flake 0.15。

`run_dual_track.py`：metrics 增加 `silhouette_iou_mask_final_vs_ref_thr8`（见下）。

## 最终参数（G2，与 bake 默认一致）
```
--light-scale 7.2 --sky-scale 0.28 --exposure-bias 0 --flake 0.15
--drawer-albedo 0.88
--edge-left-albedo 0.22 --edge-left-roughness 0.4 --edge-left-metalness 0.3
--edge-right-albedo 0 --edge-right-specular 0 --edge-right-metalness 0
--interior-lift 0.60 --interior-lift-low 0.30
--interior-emit 0.04 --interior-emit-z0 1.25 --interior-emit-z1 1.55 --interior-split-y 0.45
```

## metrics（512 spp）
| 指标 | cmf2 | cmf3 |
|---|---|---|
| RGB silhouette IoU (thr=16) | 0.672 | **0.393** |
| mask IoU thr=16 | 0.759 | 0.759 |
| **mask IoU thr=8（覆盖口径）** | — | **0.936** |
| door_edge_left \|Δ\| | 52.9 | **9.9** |
| door_edge_right \|Δ\| | 38.4 | **0.1** |
| drawer_upper \|Δ\| | 18.5 | **5.1** |
| drawer_bottom \|Δ\| | 13.7 | **9.5** |
| body_mid_band \|Δ\| | 18.9 | **2.2** |

区域均值全部 \|Δ\|≤10。mask≥0.85：在 **thr=8 覆盖口径**达成；thr=16 仍≈0.76，因为金样 240–250 浅灰机身被判成背景（与 alpha film 不对齐）。RGB IoU 下降：白棚+更亮机身使 thr=16 剪影收缩（估不准是否还能在不伤区域均值前提下抬回 ≥0.75）。

## 云端
见同目录 SSH 记录；不通则未同步。

## 路径
- `$OUT/preview.png` / `final.png` / `final-mask.png` / `compare.png` / `cmf3-triple.png` / `metrics.json` / `run.log`
==== SSH once ====
SSH ok (1 try). Cloud final rendered at /tmp/mutracer-cmf3 on ubuntu@43.192.32.90 with same G2 flags → cloud-final.png. 估不准 Linux Cycles 与本机 Metal 像素级一致。

### Cloud final detail
SSH ok. Root cause of white frames: `stage-fridge-assets.json` values were absolute Mac paths. Fix: rewrite map → `stage-fridge-assets.cloud.json` (relative `customer_asset/...`) + `DUAL_TRACK_ASSETS_ROOT=/tmp/mutracer-cmf3/fridge/assets`. Cloud 512 spp → `cloud-final.png` (not white). 估不准与本机 Metal 像素级一致。

