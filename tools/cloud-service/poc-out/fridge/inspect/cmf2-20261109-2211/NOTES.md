# cmf2: photographic post + white-studio lighting + lacquer

执行层: Claude Code / kiro/claude-sonnet-5.5。本机 Blender 5.1.1 (Metal), 1920x1080, 512 spp, OIDN 降噪。

## 结果 (metrics.json)
| 指标 | 上轮 mat-faithful | 本轮 | 基线 arch |
|---|---|---|---|
| silhouette IoU (RGB diff, thr=16) | 0.38 | **0.672** | 0.86 |
| mask IoU (alpha 覆盖, 同口径 thr=16 ref) | - | **0.759** | - |
| preview IoU | 0.80 | 0.626 (同口径新 ref) | - |
| brightness_std final / ref | 44.1 / 43.4 | 51.8 / 43.2 | |

区域均值 (final vs ref, RGB 平均 |Δ|): 抽屉上 217 vs 236 (18.5), 抽屉下 218 vs 232 (13.7), 机身中带 127 vs 148 (18.9), 左门边 1.6 vs 57.6, 右门边 38 vs 0.1。
抽屉不再死白 (上轮 255), 门边明显深于机身, 机身中带略暗于 ref。IoU 达"可接受(≥0.65)", 未到 0.75 理想线。

## 改动
- 后处理: 读 active camera 的 post_processing_settings。exposure → view_settings.exposure (加偏置 EXPOSURE_BIAS_EV=-0.5, 补 UE/Cycles 辐射量差)。temperature/saturation/contrast/gamma/gain/offset 在 Cycles 输出后做显示域近似 (numpy, 不用 compositor, 便于云端同路径)。未碰相机矩阵/RotX/swap_yz/FOV/sensor_fit。
- 白棚: 相机射线看纯白 (Strength 1.0); 其余光线 = 天光 (skylight_intensity * SKY_STRENGTH_SCALE=0.5) + 极弱 HDRI (hdri_brightness * HDRI_REFLECTION_SCALE=0.12, 只给金属反射)。Light Path "Is Camera Ray" 混合。
- 灯光: area energy = power * AREA_LIGHT_ENERGY_PER_POWER, 常数 8 (原 5, 初试 60 严重过曝)。
- Haier_CMF 漆面: Coat Weight 0.8, Coat Roughness 0.1; 亮色(luminance>=0.5)金属度上限 0.3。charcoal 不加漆。抽屉珍珠白反照率 0.80 (原 0.96 会在 Cycles 里曝到 255), charcoal 反照率 0.015 (原 0.04)。
- 玻璃: Transmission 0.9, IOR 1.45, 清玻 roughness<=0.1, Frosted>=0.3。
- 质量: run_dual_track.py 默认 1920x1080 / 512 spp。新增 --final-mask-out (alpha 覆盖 mask)。
- 调参 CLI (均有默认): --light-scale --sky-scale --hdri-reflection --exposure-bias --drawer-albedo --charcoal-albedo。
- metrics: 增加区域均值与 |Δ|、mask IoU; IoU 计算改 numpy。区域框由扫描 ref 暗条定位 (门边 x≈0.3224-0.3234 / 0.6542-0.6646)。

## 标定观察
- 剪影 IoU 对光照不单调: 内腔越亮越接近白底, 会被判成背景。light-scale 8/bias -0.5/sky 0.5 的 32spp 扫描中 IoU 最高(0.67)。
- 左门边在 ref 中约 58, 右门边约 0; Cycles 里两侧受光不同 (左 1.6, 右 38), 两侧单一反照率无法同时对齐, 差异来自面光源位置/方向。
- 内腔灰度偏暗灰, ref 内腔偏白粉; 未针对内腔单独调参。

## 云端 ubuntu@43.192.32.90
本机 4 次 SSH (ConnectTimeout=20) 均 "Connection timed out during banner exchange"; nc 探测 TCP 22 可连通。ICMP 此前已确认不通。未同步、未渲染, 无 cloud-final.png。脚本已不依赖本机路径, 通后可: rsync tools/dual-track + fridge 场景/assets, 再用同参数 --final-spp 512 运行。

## 绝对路径
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/final.png
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/final-mask.png
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/preview.png
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/compare.png
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/cmf2-triple.png (preview | final | ref, 高 1080)
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/metrics.json
- /Users/wangjianzheng/Project/git/mutracer/tools/cloud-service/poc-out/fridge/inspect/cmf2-20261109-2211/run.log
- 脚本: /Users/wangjianzheng/Project/git/mutracer/tools/dual-track/blender/blender_inner.py, run_blender_final.py, /Users/wangjianzheng/Project/git/mutracer/tools/dual-track/run_dual_track.py
