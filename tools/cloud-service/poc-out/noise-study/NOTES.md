# Noise study 2026-11-09 (Asia/Shanghai)

## 根因（实测）
`native/host/src/bin/stage_render.rs:1258` 调 `render.set_denoiser(Default::default())`，
而签名是 `set_denoiser(Option<DenoiserOptions>)` → `Default::default()` = `None` = 关闭降噪。
所以 `--denoise 1` 是空操作：同参 d0 与 d1 输出逐像素 maxdiff=1、mean=2.9e-6。
dual-track 预览、cloud worker.py（默认 denoise=True）都走这个二进制，全部未降噪。

## 验证方式（未改仓库）
APFS clone 仓库到 /tmp/mt-noise，仅把该行改成 `Some(Default::default())`，
`MUTRACER_AOT_ARCHIVE=.native-build/scene-core/render-core.lib.a cargo build --release --bin mutracer-render`，
运行时 `MUTRACER_OIDN_LIBRARY=/Applications/Blender.app/Contents/Resources/lib/libOpenImageDenoise.dylib`
（target/release/../Frameworks 下没有 OIDN dylib，不设则报 dlopen 失败）。

## 指标 noise_metric.py（960 宽 LANCZOS 统一尺度；平坦区 |Y-Gauss1.0| 均值，speckle=|res|>12 占比）
冰箱内胆 ROI 330,0,640,300：
- 原 MuTracer 32spp b3 "denoise=1"：mean 7.51 / speckle 17.6%
- 同 32spp b3 真 OIDN：1.22 / 3.4%
- 32spp b8 OIDN：1.23 / 3.7%；128spp b8：1.28 / 3.6%；256spp b8：1.31 / 3.6%
- 不降噪 1024spp b12：2.15 / 3.8%（暴力堆 spp 不如 32spp+OIDN）
- Blender 成片 64spp OIDN：1.80 / 4.9%；mat-faithful 256spp：1.73 / 4.7%
- 金样 UE PT 1024spp：2.59 / 7.5%（金样含真实纹理/细节，残差不全是噪声）
Leader 烟机 512px：原 8spp 无降噪 13.87/28.9%；32spp 无降噪 4.16/5.9%；32spp b8 OIDN 0.07/0.12%
