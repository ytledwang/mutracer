# r7 provenance: code-verified vs doc/recollection-sourced

## Code-verified (local UE project PixelStreaming, UE 5.5; see r6/sources.json)
- MRQ Path Tracer, white bg = skybox HDRI_Cubemap White, SkyLight cubemap = 4.exr, SetIntensity(skylight 0.35), SetSourceCubemapAngle(182.9) + material CubemapRotation = angle/360.
- Skybox master M_LightStage_Skybox_Master: MSM_Unlit, EmissiveColor, MaterialExpressionPathTracingRayTypeSwitch (uasset strings). Branch wiring NOT decoded.
- Camera: AEM_Manual, ApplyPhysicalCameraExposure=false, AutoExposureBias=exposure(0.8), ColorSaturation/Contrast/Gamma/Gain/Offset; AspectRatio_MaintainYFOV flag; DefaultEngine.ini bloom/auto-exposure off, Tonemapper.Sharpen=2, no OCIO.
- Inputs: r5/scene-gold329c-preview.json materials == r4/scene-gold329c-raw.json (329c snapshot); no lights; GLB-embedded colours for 钣金喷粉.布朗灰 = 0.8 (same as JSON).

## Doc / recollection-sourced (engine source not local) -- tools/dual-track/blender/ue_filmic.py ue55_post
- Manual exposure scale = 2^bias / 1.2 (EV100ToLuminance 1.2 constant).
- PostProcessCombineLUTs order; ColorCorrect in AP1 with AP1_RGB2Y luma, contrast about 0.18, pow(1/gamma).
- FilmToneMap (TonemapCommon.ush): ACES glow (0.05/0.08), red modifier (0/135/0.03/0.82), pre-desat 0.96, toe/straight/shoulder with UE 5.5 defaults slope 0.88 toe 0.55 shoulder 0.26 black 0 white 0.04, post-desat 0.93; blue correction 0.6 (ACES BlueCorrect matrix).
- Matrices: sRGB->XYZ D65, Bradford D65->D60, AP0/AP1->XYZ (ACES).
- Omitted: expand gamut, tonemapper sharpen 2, white balance != 6500 K (gold is 6500 -> identity), local exposure (scales 1), bloom (0).

## Empirical (fit to gold, not explained by source)
- HDRI rotation convention: Blender Mapping Z = UE angle - 90 deg (12 probes; mirror irrelevant).
- SkyLight -> Cycles strength factor k = 3.1 (units predict 1; 3.0..3.2 flat, ~pi). Open question.
- White skybox leak into lighting: 0 (best), consistent with the RayTypeSwitch.
