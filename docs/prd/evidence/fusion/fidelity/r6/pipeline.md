# 可影 1.0 渲染链路还原（金样任务 329c202e）

> 依据本机源码与金样任务快照，说明为什么同一台冰箱在可影里会得到 `fridge-ref-front-329c.png`。本文不改渲染代码。所有断言都给出路径与字段；源码里找不到的，写入「尚未核实」，不编造。
>
> 金样任务快照：`docs/prd/evidence/fusion/fidelity/r4/gold-render-task-329c202e-render_data.json`（从 `my-stage-hk/local-stack/backup/20261024-202722/tables/render_task.json` 抽出）。任务 id `329c202e-e89a-48c0-aa04-59a360510cbd`，名称「冰箱体.fbx-[单品渲染]_06251729」，创建于 2025-06-25 17:29（Asia/Shanghai），`file_id` `1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a`，`status=succeed`，`image_url=s3://render_results/329c202e-e89a-48c0-aa04-59a360510cbd`。本机金样图：`tools/cloud-service/poc-out/fridge/ref/fridge-ref-front-329c.png`（7680×4320 RGBA，alpha 全 255）。

## 1. 场景是谁写的

可影前端（`/Users/wangjianzheng/Project/HG/my-stage-hk`，文档也称 dyson/my-stage-main）是场景编辑器，不负责最终成片。`docs/3D-EDITOR-ANALYSIS.md` 写明：主画面是 UE5 Pixel Streaming 经 WebRTC 推过来的；前端只维护一份与 UE 同步的 JSON 场景图，编辑命令经 DataChannel 发给 UE。

场景图字段定义在 `types/stage.ts`：`cameras` / `environments` / `lights` / `models` / `meshes` / `materials` / `textures` / `views` / `scene_settings`。金样 `scene_json` 就是这份结构的快照，在点「渲染」时与 `render_settings` 一起写入 `render_task.render_data`（见下一节）。

金样 329c202e 的场景是**单品场景**，不是厨房模板融合：

- 视图 `298cfe60-923d-44fb-a0d1-f2206b9a48e1`（Front）：`active_camera` = `858db55c-...`，`active_environment` = `ab403659-...`（环境「4」）。`model_group_visibility` 只开关产品组，没有厨房壳。
- 环境「4」：`background_type` = `white`，`hdri_brightness` = 10，`skylight_intensity` = 0.35，`hdri_contrast` = 1，`hdri_resolution` = 128，`hdri_angle` = 182.9，`use_sun_light` = false，`image` = 纹理 id `06fbbc51-...`，对应 `official_asset/environment/8ffebd47-fb14-4175-bcac-dd9a175b7bde/textures/4.exr`。
- 灯光：`lights.00000000-...`（`light_root`）的 `children` 为空。任务里**没有一盏面光**。
- 模型：486 个 model；网格从 `customer_asset/...` 的 GLB 拉取（UE 端 `SpawnMeshAsync`）。
- 这与后来 MuTracer r2/r5 用的「厨房壳 32 盏 RectLight + 自拟 16.exr 环境」不是同一条输入链。厨房融合（`replace_id` / scene_template）是另一条产品线，**没有进入 329c202e 的 payload**。

前端提交对话框不会自动插入「[单品渲染]」这几个字（`components/editor/panel/render/dialog.tsx` 默认任务名是 `sceneName_时间戳`）。项目页 `app/project/[id]/layout.tsx` 有「选择单品渲染文件」的注释，指的是选产品文件，不是另一套渲染器。任务名里的「[单品渲染]」应理解为产品单品场景，而不是单独的引擎模式。

## 2. 任务如何提交

提交入口：`components/editor/panel/render/dialog.tsx` 的 `handleRender`。

1. 用 `defaultImageRenderSettings` 做底：`render_type: 'image'`，`aa_spatial_samples: 512`（UI 选项里 1024 是「1024 High Quality」），`aa_temporal_samples: 1`，`max_bounces: 32`，`denoise: true`，`base_color: true`，`output_format: 'png'`，`output_scale: 1`（可改为 0.5/1/2/4）。
2. 对每个勾选的视图，按 **当前相机 `frame_size * output_scale`** 写入 `views_in_task[].resolution`（`dialog.tsx` 约 231–238 行）。UE **不读** `output_scale`：`JsonStructs.h` 的 `FJsonRenderSettings` 没有该字段；`RenderActor.cpp` 只用 `views_in_task` 的 resolution。
3. `supabase.from('render_task').insert({ render_data: { render_settings, scene_json }, file_id, project, user_id, name, type })`（表名 `utils/supabase/constant.ts` 的 `RenderTaskTableName`）。

金样实际 payload（已核对任务行）：

| 字段 | 值 |
| --- | --- |
| `render_settings.render_type` | `image` |
| `aa_spatial_samples` | **1024**（用户选了 High Quality，不是默认 512） |
| `aa_temporal_samples` | 1 |
| `max_bounces` | 32 |
| `denoise` | true |
| `base_color` | true（其余 AOV 全 false） |
| `output_format` | png |
| `output_scale` | 4 |
| `views_in_task` | 仅 Front `298cfe60`，`resolution: [7680, 4320]` |
| 相机 `frame_size` | `[3840, 2160]` |

这里有一处**已确认的不一致**：按**当前**前端公式，`3840×2160 × output_scale 4` 应是 15360×8640，但任务里写成了 7680×4320，而金样 PNG 正好是 7680×4320。UE 只认 `views_in_task.resolution`，所以实际出图就是 8K。`output_scale=4` 相对 1920×1080 也是 7680×4320。2025-06 的提交 UI 是否用另一套倍率、或是否有 8K 上限，在当前 `dialog.tsx` 里看不到，列入「尚未核实」。不要用 `frame_size * output_scale` 反推金样分辨率。

生产调度（不是 2026 年那台用 Blender 的远程测试机）：

1. `dyson/job-creator-main` 监听 Supabase `render_task` 的 INSERT，向 Nomad 注册一个占用 `gpu=1` 的 job（`job_creator.py` / `nomad_job.py`）。
2. Nomad 任务在 UE 渲染机上把该行的 `render_data` 写成 `<RENDER_PATH>/<taskId>/render_task.json`。
3. UE 以 `-RenderWatchDir=` 启动，`ARenderActor::BeginPlay`（`RenderActor.cpp` 第 92 行）监视该目录；看到 `render_task.json` 且没有 `done.txt` 就开始。
4. 完成后写 `done.txt` / `progress.txt`；Nomad 侧把目录里的图上传到桶 `render_results/<taskId>/`，回写 `image_url=s3://render_results/<taskId>`、`status=succeed`。

本地等价说明见 `my-stage-hk/local-stack/ARCHITECTURE-LOCAL.md` 与 `local-stack/render-bridge/bridge.py`。注意：`ARCHITECTURE-REMOTE.md` 里 43.192.32.90 的 `stage-render-worker` 是 **2026 年用 Blender Cycles 的测试环境**，不是 2025-06 金样的生产路径。金样走的是 Render2 UE 渲染机（角色见 `/Users/wangjianzheng/Doc/dyson/aws.md` 的主机表：`Render2-render-asg` 为 g4dn GPU 机器，`Render2-supabase` 为 10.160.9.143；本文不抄写任何密钥）。

## 3. 渲染引擎

工程：`/Users/wangjianzheng/Project/HG/dyson/PixelStreaming/PixelStreamingDemo.uproject`，`EngineAssociation` = **5.5**。模块 `PixelStreamingDemo`，启用插件 PixelStreaming、MovieRenderPipeline、glTFRuntime、MoviePipelineMaskRenderPass。本机还有一份日期为 2025-06-25 的 `PixelStreaming-main`，`Source` 与当前树一致。

离线出图不是视口截屏，而是 **Movie Render Queue + Path Tracing**：

- `ARenderActor::RenderWithExecutor`（`RenderActor.cpp` 约 469–476 行）：当 `RenderType == ERenderType_BaseColor`（由 `render_settings.base_color=true` 入队，约 270 行）时，`bUsingPathTracing=true`，`JobConfiguration->CopyFrom(PipelineConfig)`。
- `PipelineConfig` 指向关卡里 `BP_RenderFileWatcher` 上的 `UMoviePipelinePrimaryConfig`。对应资产是 `Content/Sequencers/dc_1080p24_HQ.uasset`（字符串含 `++UE5+Release-5.5`、`MoviePipelineDeferredPass_PathTracer`、`MoviePipelineImageSequenceOutput_PNG`、`MoviePipelineAntiAliasingSetting`、CVar `r.PathTracing.Denoiser` 与 `r.Tonemapper.Sharpen`）。辅助通道走 `dc_1080p24_HQ_Deferred.uasset`（Deferred + EXR ObjectId）。这两份 uasset 是二进制，空间/时间样本的**默认数字**无法在本文可靠读出；任务会覆盖 AA。
- 覆盖：`UMoviePipelineAntiAliasingSetting::SpatialSampleCount = aa_spatial_samples`（金样 1024），`TemporalSampleCount = aa_temporal_samples`（1）。这就是 Path Tracer 的 spp 来源。`RenderActor.cpp` 在「SPP 设置」注释下实际只写了 `PathTracingMaxBounces = max_bounces`（32），**没有**在离线路径里写 `PathTracingSamplesPerPixel`。
- Denoise：`UMoviePipelineConsoleVariableSetting` 设置 `r.PathTracing.Denoiser` 为 1 或 0（金样为 1）。项目 `DefaultEngine.ini` 另有 `r.PathTracing=True`、`r.RayTracing=True`、`r.RayTracing.Skylight=True`。
- 每个 unit 先 `SetRenderView(viewId)`，再等 1 秒 timer 后 `RenderWithExecutor`（`RenderActor.cpp` 约 355–369 行），给 SkyLight capture 留时间。
- `SetRenderView`（`HaierJsonBlueprintFunctionLibrary.cpp` 约 164–228 行）：把玩家视角切到该视图相机、按视图的 `active_environment` 调用 `SetEnvironmentSettings`、按组可见性隐藏物体、挂材质。金样 Front 因此用环境「4」，而不是 `scene_settings` 里可能不同的默认环境。

环境「white」在 UE 里的真实含义（`SetEnvironmentSettings`，约 2336–2390 行）——这是外观的关键，也是 r4 里「白底当恒定 1.0 天空」假设需要纠正的地方：

- 可见天空球（`BP_LightStudio` 上 tag 为 `Skybox` 的 mesh）换成立方体贴图 `/Game/Blueprints/Assets/White.White`，所以**相机看到的背景是白的**。
- **SkyLight 仍然异步加载真正的 4.exr**（`SetTextureAsync(settings.image, ..., bCubemap=true)`），`SkyLightComponent->SetCubemap`。也就是说：白的是背景，照亮物体的是 4.exr。
- `hdri_brightness=10` 写在 **天空球材质** 参数 `HDRI_Brightness` 上，不是 SkyLight 强度。白背景下它对「看见的白」有影响，对 4.exr 照明的影响取决于该材质是否还参与 lighting（资产是二进制，列入尚未核实）。
- `skylight_intensity=0.35` → `SkyLightComponent->SetIntensity(0.35)`。
- `hdri_angle=182.9` → 材质 `CubemapRotation = 182.9/360`，同时 `SkyLightComponent->SetSourceCubemapAngle(182.9)`。
- `use_sun_light=false` → 关掉 Direct Light。
- `hdri_resolution=128` → `SkyLightComponent->CubemapResolution = 128`。

模型加载：`SpawnMeshAsync` 对 `meshes[url]` 向 `SupabaseUrl + /storage/v1/object/sign/<url>` 申请短时签名再下载，用 glTFRuntime 生成 Actor，再 `ActorSetMaterialAttr`。本文不记录任何密钥或签名 URL。

## 4. 相机后期

金样相机 `858db55c` 的 `post_processing_settings`：

`exposure=0.8`，`gamma=0.9`，`contrast=1.2`，`saturation=0.8`，`temperature=6500`，`gain=1`，`offset=0`，`vignette=0`，`bloom_intensity=0`，`bloom_threshold=-1`，`bloom_scale=0`，`highlight_contrast=1`，`shadow_contrast=1`。没有 `slope` / `toe` / `shoulder` / `black_clip` / `white_clip`。

UE 映射在 `UHaierJsonBlueprintFunctionLibrary::ActorSetCameraAttr`（`HaierJsonBlueprintFunctionLibrary.cpp` 约 2095–2202 行）。条件是字段大于各自的哨兵值才 `bOverride_* = true`。金样的对应关系是：

| JSON 字段 | 条件 | UE `FPostProcessSettings` |
| --- | --- | --- |
| `exposure` 0.8 | `> -20` | `AutoExposureBias = 0.8` |
| `temperature` 6500 | `>= 0` | `TemperatureType = TEMP_ColorTemperature`，`WhiteTemp = 6500` |
| `saturation` 0.8 | `>= 0` | `ColorSaturation = (0.8,0.8,0.8,1)` |
| `contrast` 1.2 | `>= 0` | `ColorContrast = (1.2,1.2,1.2,1)` |
| `gamma` 0.9 | `>= 0` | `ColorGamma = (0.9,0.9,0.9,1)` |
| `gain` 1 | `>= 0` | `ColorGain = (1,1,1,1)` |
| `offset` 0 | `>= -1` | `ColorOffset = (0,0,0,0)` |
| `vignette` 0 | `>= 0` | `VignetteIntensity = 0` |
| `bloom_intensity` 0 | `>= 0` | `BloomIntensity = 0` |
| `bloom_threshold` -1 | `>= -1` | `BloomThreshold = -1` |
| `highlight_contrast` 1 | `>= -1` | `LocalExposureHighlightContrastScale = 1` |
| `shadow_contrast` 1 | `>= -1` | `LocalExposureShadowContrastScale = 1` |
| `slope/toe/shoulder/white_clip` 缺省 | 不满足 `>= 0` | **不 override**，沿用工程默认 |

相机创建时还有固定默认（约 1507–1526 行），金样一定带上：

- `AutoExposureMethod = AEM_Manual`
- `AutoExposureApplyPhysicalCameraExposure = false`（不走光圈/快门物理曝光）
- `LensFlareIntensity = 0`
- `PathTracingEnableReferenceDOF = true`，`PathTracingEnableReferenceAtmosphere = false`
- `bConstrainAspectRatio = false`，`AspectRatioAxisConstraint = AspectRatio_MaintainYFOV`，`SetFieldOfView(fov)`，金样 `fov=35`，`sensor_width=24.576` 只进 `DepthOfFieldSensorWidth`（金样 `dof=false`）

项目默认（`Config/DefaultEngine.ini` `[/Script/Engine.RendererSettings]`）：

- `r.DefaultFeature.AutoExposure=False`（方法标记为 2，但功能关闭；相机仍 Manual + Bias）
- `r.DefaultFeature.Bloom=False`，`r.DefaultFeature.LensFlare=False`，`r.DefaultFeature.MotionBlur=False`
- `r.DefaultFeature.LocalExposure.HighlightContrastScale=0.8` 与 Shadow 同为 0.8，但金样相机把两项 override 成 **1**（不做局部曝光压缩）
- `r.Tonemapper.Sharpen=2`
- `r.PostProcessing.PropagateAlpha=1`
- `r.Substrate=True`
- **没有** Working Color Space / OCIO / `r.TonemapperFilm` / ACES 项目级覆盖

因此必须**纠正 r4 的表述**：不能把「任务里没写 tonemapper 字段」直接说成「已证实使用默认 filmic，高光钉在约 236」。源码只证明：后期是 UE 内置 Color Grading（`ColorSaturation/Contrast/Gamma/Gain/Offset`）再加上 **UE 5.5 工程未覆盖的默认 Tonemapper**。FilmSlope/Toe/Shoulder/WhiteClip 未被金样覆盖，所以旧版 UE4 Filmic 旋钮没有被这笔任务打开。UE 5.5 默认 Tonemapper 一般是 ACES 拟合曲线，但这是引擎默认，不是本仓库里的一行赋值；本机也没有引擎着色器源码可核对。金样抽屉高光约 236、背景均值约 254.4，与「有肩部的胶片/ACES 曲线」相容，但 236 不是代码里的常量。

Color Grading 的**精确运算顺序与 0.18 支点**在引擎 `ColorCorrect` 着色器里，本仓库没有。项目只做字段映射。r5 的 `ue_filmic.py`（对比约 0.18、再 `pow(1/gamma)`、再 ACES fitted、再 sRGB）是对这条链的近似，不能再写成「已由可影源码证实的公式」。MuTracer 默认路径 `blender_inner.py` 的 `display_post` 是另一套：在 Standard 显示域里做 `(x-0.5)*contrast+0.5` 再 `x**gamma`，与 UE 不一致。

## 5. 材质

金样 126 个材质。`FJsonMaterial` 本身只有 `master` + 三个 map；扁平字段在 `SceneContext.h` 的 `ConvertToMaterialParamStruct`（约 314–344 行）里拆开：

- `master` → `/Game/Materials/Masters/<master>`（`ActorSetMaterialAttr` 约 1804 行）后创建 Dynamic MI
- `*_scalar` → `scalar_params[GetUEKey]`，如 `roughness_max_scalar` → 参数名「Roughness Max」
- `*_tex` → `texture_params["Tex_"+GetUEKey]`
- 长度为 3 的数组（如 `base_color_rgb`）→ `vector_params[GetUEKey]`（「Base Color」）

`GetUEKey` 按 `_` 分段、首字母大写、丢掉最后一段类型后缀。

金样 master 计数：`M_Opaque_Master` 104，`M_Glass_Default_Parent` 7，`Haier_CMF_01` 6，`M_Opaque_MetalFingerprints_Parent` 2，`Haier_CMF_05` 2，`Haier_CMF_06` 2，以及 Fingerprints / Emissive / FingerprintsDust 各 1。对应 uasset 都在 `Content/Materials/Masters/`。图是 Substrate 材质图，二进制，节点与默认值无法从源码读出。

r4 已核对：当前产品场景里 126 个材质有 5 个在金样之后被改过（例如「05玉墨银」底色 0.165→约 0.83/0.86，`Plastic_Rough` 0.21→0.61，`Plastic_Coated` 的底色与 `roughness_max`，`Metal_Frosted` 的磨损强度）。要对齐金样，必须用 **329c 任务快照里的材质值**，不能用后来的产品 `scene.json`。

纹理同样走 Storage 签名下载；环境 4.exr 的 `format` 为 `TC_HDR_COMPRESSED`，`SetTextureAsync(..., bCubemap=true)` 按立方体加载。

## 6. 输出

- 分辨率：MRQ `OutputSetting->OutputResolution = views_in_task.resolution` = **7680×4320**。不是从更大的图再降采样。本机 `fridge-ref-front-329c.png` 就是这个尺寸；MuTracer 指标用的 1920×1080 是后来 LANCZOS 缩小的。
- 文件名：`FRenderUnit::GetUniqueName()` = `{TaskId}_{ViewId}_base_color`，即 `329c202e-e89a-48c0-aa04-59a360510cbd_298cfe60-923d-44fb-a0d1-f2206b9a48e1_base_color`（`RenderActor.h` 约 35–37 行）。静帧 `CustomEndFrame=1`，`FileNameFormat` 不含帧号。本机文件名是后来改的。
- 格式：Path Tracer 配置启用 `MoviePipelineImageSequenceOutput_PNG`（8 bit，经 Tonemapper 后的显示域）。金样图 RGBA 且 alpha 全 255：白背景来自可见的 White 天空球，不是透明底再合成。
- 上传：产物进 `render_results/<taskId>/`，数据库 `image_url=s3://render_results/<taskId>`。没有单独的 LUT 文件或离线合成步骤写在任务或 RenderActor 里。
- `r.PostProcessing.PropagateAlpha=1` 存在，但金样走的是不透明白天空球，所以对这张 Front 金样几乎看不见透明通道。

## 7. 其它会影响外观的因素

- **灯光单位**：若场景有灯，`SpawnLight` 把 `ULocalLightComponent::IntensityUnits = ELightUnits::Candelas`，`SetIntensity(power)`，RectLight 的 `size_x/size_z` 直接当厘米源宽高（`HaierJsonBlueprintFunctionLibrary.cpp` 约 1454、1986–2032 行）。金样没有灯，这条不影响 329c，但厨房融合场景会受影响。MuTracer 默认是 `power * --light-scale`（默认 7.2），单位不同。
- **HDRI 朝向**：UE 是 `SetSourceCubemapAngle(度)` + 材质 `CubemapRotation=度/360`。Blender 的 Z 旋转约定未必相同。r5 按 182.9° 转了仍左右不对称，说明约定或捕获方式还没对齐。
- **曝光**：全局 AutoExposure 关闭；相机 Manual + `AutoExposureBias=0.8`；关闭物理相机曝光。没有自动测光在跑。
- **Bloom / 眩光 / 运动模糊**：项目默认关；金样 BloomIntensity=0、Vignette=0。
- **局部曝光**：金样 Highlight/Shadow Contrast Scale = 1，等于关掉项目默认的 0.8 压缩。
- **FOV 轴向**：代码把 FOV 设成 `AspectRatio_MaintainYFOV` 且 `fov=35`。按 UE 文档这是**垂直** FOV。但 r2 用 Blender **水平** FOV 35 时，与金样的暗部包围盒几乎重合（x 591–1278 vs 590–1278）。MRQ 仍绑定 `LS_RenderSequence.uasset`，静帧把 `CurrentViewId` 清空并 `SetViewTarget`。序列里的相机是否覆盖轴向，uasset 读不出来。列为尚未核实，先不要改 MuTracer 的 FOV。
- **Substrate、Lumen、MegaLights** 在 `DefaultEngine.ini` 里为项目默认；离线 BaseColor 走 Path Tracer，实时视口才是另一套。不要把视口 Lumen 外观当成金样。
- **白立方体 `/Game/Blueprints/Assets/White.White`** 与天空球材质 `M_LightStage_Skybox_Master` 是 uasset，线性值是否为 1、亮度 10 如何进 Path Tracer，源码看不到。

## 8. MuTracer 应如何跟随

只建议顺序，这一步不改代码。目标是复现 329c 的输入与算子，而不是继续在厨房融合灯光上调曲线。

1. **先对齐输入，再谈调参。** 金样是单品 + 环境「4」+ 白背景 + 无灯 + 任务快照里的材质和相机后期。r2 用厨房 32 盏灯和自拟 16.exr（亮度 0.8）是另一套照明，全图误差再降也解释不了「同一模型为什么在可影里是那张图」。用 `r4/scene-gold329c-raw.json`（或同内容的 preview）做基准，不要用后来改过 5 个材质的产品场景。
2. **按 UE 的方式拆环境。** 相机射线看 White 立方体；SkyLight 用 4.exr、强度 0.35、角度 182.9°；不要把 `hdri_brightness=10` 乘进 Cycles world strength 就当成「UE 的 10」。先做一次与 `SetEnvironmentSettings` 同结构的拆分（可见背景 vs 照明立方体），再标定强度。
3. **后期要对 `FPostProcessSettings`，不要对 `display_post`。** Manual + Bias 0.8，ColorSaturation/Contrast/Gamma/Gain/Offset 走 UE Color Grading，局部曝光为 1，不开 Bloom。Tonemapper 用 UE 5.5 默认（优先可验证的 ACES 拟合，而不是 Standard 显示域的对比度）。r5 的 `--tonemap ue-filmic` 方向对，但公式还不是源码实证；下一步应对照引擎文档或一次线性 EXR 调试，而不是再猜一条曲线。默认路径必须继续保持 Standard、无开关时行为不变。
4. **材质用官方 Master，不要只用 Principled 近似。** 参数名按 `GetUEKey` 规则喂给对应 MI。金样大量是 `M_Opaque_Master` 和 `Haier_CMF_*`、玻璃是 `M_Glass_Default_Parent`。图是 uasset，若要可复现，需要在 UE 里打开或导出节点，而不是在 Blender 里继续猜清漆。
5. **采样与分辨率按任务走。** 1024 spatial × 1 temporal、32 bounce、denoiser on；比较时用 7680×4320 再缩到 1920，或与金样同一套缩放。
6. **灯光单位先记下来，这一枪用不上。** 将来融合厨房灯时，UE 是 Candela + 厘米尺寸，不能直接套 `--light-scale 7.2`。
7. **FOV 与 HDRI 轴向先做一次对照实验，再改代码。** 目前代码写的是 Y-FOV，成片包围盒又像水平 35°；HDRI 182.9° 也还没对上左右受光。这两项会改造型，值得单独做只读对照，不要和曝光改在一起。
8. **不要把 2026 远程 Blender worker 或厨房融合模板当成 1.0 金样路径。** 金样就是 Render2 上的 UE 5.5 Path Tracer + Movie Render Queue。

## 9. 尚未核实

1. UE 5.5 默认 Tonemapper 的精确曲线与 Color Grading 运算顺序（引擎着色器不在本机仓库）。ACS/filmic「高光约 236」只是金样统计，不是命名常量。
2. `dc_1080p24_HQ.uasset` / `LS_RenderSequence.uasset` / `BP_LightStudio` / `White.White` / 各 Master 材质图均为二进制，MRQ 默认分辨率、序列相机、白立方体线性和 CMF 节点无法在本文中读出。
3. `hdri_brightness=10` 在白背景下除了改变可见天空球，是否还影响 Path Tracer 里的照明。
4. `output_scale=4` 与 `frame_size` 3840×2160、实际 7680×4320 之间，2025-06 前端的具体计算。
5. `AspectRatio_MaintainYFOV` 在 Movie Pipeline 出图时是否仍然生效（与金样/r2 包围盒几乎重合之间的矛盾）。
6. 生产 Render2 机上的 PixelStreaming 构建号是否与本机 2025-06-25 源码树完全一致（本机 Source 与 `PixelStreaming-main` 一致，但没有构建哈希）。
7. 金样 PNG 从 `render_results` 拉到 `fridge-ref-front-329c.png` 时是否经过再压缩；尺寸与任务分辨率一致，未见二次降采样的证据。
