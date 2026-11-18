# Blender Web 3D × MuTracer 融合：第 0 步现状差距

> 2026-11-10（Asia/Shanghai）。对照 `docs/prd/Blender-Web-3D与MuTracer融合设计.md` 与现有 viewer / 双轨 / 模板代码，只写差距与改哪些文件，**不改代码、不提交**。
>
> 阅读对象：Koa（确认后再动手）、MuTracer-POC（落地）。
>
> 配套：`docs/prd/可影2.0-需求说明.md`、`docs/technical/dual-track-render.md`、`tools/dual-track/stage_semantics.md`、`tools/scene-template/README.md`、`docs/technical/scene-template-fusion-scout.md`、`docs/technical/import-greenpath-m3.md`。

## 硬边界（本文建议均不得突破）

- 可影交付仍是：**棚拍壳 + 云端出图 + 可下载**。成片仍只走 Blender Cycles（`tools/dual-track/blender`）。
- **实时查看不是成片**，不能拿实时截图冒充效果图；也不做独立网页展厅。
- **不要在 viewer 里重造模板合并**（`replace_id`、占位替换、views）。合并仍在 `tools/scene-template`（可影语义薄层），viewer 只消费合并结果。
- **Living Room 不要改成模板**。`viewer/src/engine/model-presets.json` 的 `research-living-room` / `research-living-room-2` 仍是房间 / 环境资产，不进「场景模板」列表，也不给 `ModelPreset` 加 `replace_id`。
- 不把现有 `previewEnabled`（路径追踪交互中的低分辨率预览）和本次「实时查看」混成一个开关。
- 不发明第二套 scene 格式：三层共用现有 **scene JSON + asset map**（`stage_semantics.md`）。

## 0. 已拍板（2026-11-10 ~18:58 Asia/Shanghai，Koa）

编码仍不放行：收到 Koa 明确说「可以开写」之前，**headless=0，不动代码，不换其他模型，不用 Claude Code，不改全局 DSH profile**。下面 7 点按此执行，不再等问。

1. **viewer 消费合并结果走 A。** 给 viewer 加只读 `scene.json` + asset map 适配，映射到已有 Three 场景、相机、显隐、材质。资产仍按 map 里的 GLB 加载。不要把「先导出整场景 GLB 再 `loadFiles`」当主契约，不要在 viewer 里重造合并或第二套格式。
2. **成片维持 Standard。** 不要改 `blender_inner.py` 的 `view_transform`，以免动金样对照。实时查看跟现有 viewer AgX，高质量预览保持现有 AgX。F4 验收是色相不乱跳、允许实时更亮，不是三层像素级套同一条曲线。成片改 AgX 要另独拍板并重做金样。
3. **本轮「提交渲染」接到本机 `run_blender_final.py`**，传同一份 scene.json + asset map + 当前相机/视图。8787 继续只做预览。云端 Blender 不是 F1/F2 验收门槛；提交口的数据形态要和双轨成片一致，方便以后接云端，不要另写一套。
4. **官方厨房壳 `RF_Kitchen_0302_Scene`（`ccdaa114-…`）的 GLB 仍不在本地**：不要假装有壳，也不要擅自拉全量官方桶。F1 用带命名材质和 Pivot 的好样件（优先冰箱单品或现有工业减速器），不用 Living Room。F2 用现有本机 M2 夹具：`tools/scene-template/fixtures/real/template-fridge-kitchen.json` + 冰箱单品，`replace_id` `c83a2f4a-…`。验收材料写明：官方壳缺失，合并预览里厨房 mesh 会被隐藏，本轮 F2 验的是状态同步和模式切换，不是完整厨房空间光感。**F3/F5 等官方壳补到本地再做。**
5. **允许本轮改 `merge_scene_template.mjs`**：只补 `meshes[*].url` 改写、`views` remap、以及不要丢弃 F2 切视图所需的产品相机。保持可影合并语义，不重写、不把修复做进 viewer，不必等可影。修完写进验收材料。
6. **两条 `replace_id` 不要混成一条。** 面板/产品目录以可影模板表为准：冰箱厨房官方是 `ccdaa114-…`，壳未到齐时这项标为不可验收，不要改成 M2 的 ID。本轮 F2 开发夹具以本机备份场景为准：`c83a2f4a-…`。官方壳到位后，F3/F5 再切到 `ccdaa114-…`。
7. **F1 验收主路径：命名材质的 GLB**（FBX 转完能保名的也可）。STP：转换后必须跑契约校验，缺材质/无单位换算要失败或显式警告，禁止静默出坏文件——这扇门算 F1 范围。把 STP 补材质和 mm→m 做成可卖转换，另列缺口，不挡 F1 主路径过关。

---

## 1. 设计要求摘要（摘自融合设计文，非空话）

**F1 导入导出契约：「名字就是契约」。** 必须保留网格 / 节点名、源文件材质名、名称含 `Pivot` 的转动节点、相机名、占位或 `replace_id` 对应节点。允许 Draco / meshopt / 纹理压缩与静态合批，但合批不得越过动画或枢轴祖先，不得把不同材质合并到丢掉名字。默认路径禁止会破坏上述名字的 `flatten` / `prune` / `palette`；若必须开，校验要显式失败。导入时做契约检查并写日志 / 提示用户。契约同时约束「进编辑器的模型」和「成片轨道再导出的网格」。落地优先在导入链和 dual-track 使用的 GLB 准备步骤，不先改路径追踪内核。验收：带命名材质和转动枢轴的样件（优先冰箱 / 洗衣机或工业减速器，**不用 Living Room**）走完「优化导出 → 导入 viewer → 按名绑材质 → 套模板或切机位」；不允许「导出后基色被洗白」且无报错。

**F2 实时查看接入 viewer，与物理预览并存。** 现有预览几乎一进就是路径追踪。要在现有 viewer 增加两种明确模式，且**不要借用 `previewEnabled` 这个名字**：实时查看（光栅、可流畅转圈，合批 / 自适应画质 / `compileAsync` 后再揭开画面）；高质量预览（现有 MuTracer 路径追踪，保持预览轨道语义）。默认进实时查看；一键切高质量预览时继承当前相机 / 视图、物体显隐、已赋材质、已合并的模板结果。套模板后先在实时查看里看到结果，再允许进高质量预览或提交成片。实时查看复用已加载的 Three 场景或同一份 scene 状态，不另开只读演示站，本阶段不做「导出独立展厅 HTML」。验收：同一份已合并场景，实时下切正视图 / 特写再切高质量预览，相机与材质一致；单品 + 模板在开发机上约 2 秒内可转；文案能分清「实时查看 / 高质量预览 / 提交渲染」。

**F3 场景模板预烘焙光照。** 烘焙对象是模板壳，不是被替换进去的产品。烘焙结果随模板资产走，合并 `scene.json` 时由模板带入；产品换掉占位后壳上的烘焙仍在。实时查看优先用这套烘焙；高质量预览和成片仍用模板物理灯 / 环境，不把 lightmap 当成成片光源。无烘焙资产时实时查看回退普通实时光，不能报废模板。已知合并缺口（`meshes[*].url` 未改写、`views` 未 remap 新根 id）要在启用烘焙前先避开或先修。烘焙逻辑不写进 `merge_scene_template.mjs` 的占位替换里。

**F4 材质身份与色彩管理对齐。** 三层共用 scene 里的颜色、金属、粗糙度、贴图。实时查看色调映射默认与 viewer 已有 AgX 对齐，避免第三套电影曲线。按材质名的实时着色增强只能键在契约保留的材质名上，不得带到高质量预览 / 成片。成片特殊材质（CAD 调试塑料、门边粉末涂料、近白抽屉、玻璃）继续只存在成片轨道。验收：2–3 个已有样件材质（含金属、玻璃）三层并排对照，色相不乱跳；实时允许更亮，但不把黄铜做成浅灰。

**F5 性能与画质档。** 实时查看提供可理解档位（如流畅 / 标准）：自适应分辨率、合批、按需阴影。高质量预览沿用现有采样、降噪、分辨率，互不影响。用真实模板场景（优先厨房冰箱或洗衣机，**不用 Living Room 充数**）给出帧时间和档位差异；切档不得丢掉材质名或相机。

落地顺序（设计第 5 节）：第 0 步（本文）→ F1 → F2（本轮验收核心）→ F3 → F4/F5。不得倒过来先做烘焙和 shader。

---

## 2. 现状对照

### F1 导入导出契约 — 缺官方预设，也缺导入校验

**已有**

- Viewer 只直接吃 GLB / glTF / PBRT。入口：`viewer/src/components/Toolbar.tsx`（`OpenMenu`，`accept` 含 `.fbx/.stp/.step`）→ `ViewerEngine.loadFiles`（`viewer/src/engine/ViewerEngine.ts` L306）→ `loadModelFromFiles` / `parseModelSource`（`viewer/src/engine/loadModel.ts`，Three `GLTFLoader` + Draco / Meshopt **解码**）。
- FBX / STP 不能在浏览器里解析。`droppedFiles.ts` 的 `isConvertibleModelFile` / `convertHint` 只 toast 指向转换脚本，见 `docs/technical/import-greenpath-m3.md`。
- 转换脚本存在，但导出是 Blender 默认参数，没有名字契约：
  - `tools/import-smoke/convert_fbx_to_glb.sh` L14：`bpy.ops.export_scene.gltf(..., export_format='GLB')`
  - `tools/import-smoke/convert_stp_to_glb.sh` L35：同上；gmsh→STL 路径无材质、无 mm→m 单位换算
  - `tools/cloud-relay.py` L171 / L178：同样裸导出
- 加载侧会保留 glTF 里自带的 `material.name` / 节点名（Three 解析），材质面板展示名字（`MaterialPanel.tsx`）。这不是契约检查，坏文件也能静默进编辑器。
- 双轨预览 / 成片已按 mesh 消费 `scene.materials` 身份：`native/host/src/bin/stage_render.rs` 的 `override_imported_material`（约 L688，写入 name / color / metallic / roughness / 贴图）；`tools/dual-track/blender/blender_inner.py` 的 `material_override` / `blender_material`（约 L251、L373）。约定见 `tools/dual-track/stage_semantics.md`。

**缺什么**

- 仓库里**没有**「可影 / MuTracer 导入导出契约」官方预设，也没有 `gltf-transform` 管线。不存在对 `flatten` / `prune` / `palette` 的显式禁止或失败校验。
- 导入时**没有**契约检查：缺材质名、枢轴被拍平、仅有默认材质、占位节点找不到，都不会作为失败或警告交给用户 / 日志。
- STP 转换产物本身就会「仅有默认材质」（`import-greenpath-m3.md`），按 F1 验收会被判不合格，且现在不会报契约失败。
- 成片轨道没有「再导出网格」的受约束预设；若后续优化 GLB，没有门禁防止洗掉名字。
- 验收样件（命名材质 + `Pivot` 转动节点，冰箱 / 洗衣机或减速器）尚未作为 F1 固定夹具列出（不要用 Living Room）。

### F2 实时查看 ↔ 高质量预览 — 现在只有一层路径追踪

**已有**

- Viewer 一加载就走 MuTracer 路径追踪。`Viewport.tsx` 画布 aria-label 写的是 “Path traced view”；`ViewerEngine` 构造里 `RenderLoop` 的 `select`（L194）为：`previewEnabled && changing ? 'preview' : 'final'`，两者都是路径追踪，差别只是交互中的低分辨率预览。
- `store.ts`：`previewEnabled` 默认 `true`（L168），UI 文案是 **「Interactive preview」**（`DebugOverlay.tsx` L122–127，另有 `previewMaxResolutionScale`）。这正是设计第 2 节要求**不要混用**的那个开关。
- 高质量预览轨道（头less）已通：`native/host/target/release/mutracer-render` / `tools/dual-track/run_dual_track.py preview`，以及云服务 `tools/cloud-service/`（`README.md` 写明 **preview-only**；`worker.py` 调 `mutracer-render`，默认 `--tone-mapping agx`）。
- 成片轨道已通：`tools/dual-track/blender/run_blender_final.py` + `blender_inner.py`。云端 8787 **不是**成片。
- 右栏「场景模板」已挂上：`store.ts` `InspectorTab` 含 `'scene-templates'`；`Inspector.tsx` `TABS` / `PANELS`；`App.tsx` 数字键 `1-5`。`SceneTemplatePanel.tsx` 只读 `scene-templates.sample.json`，不执行合并，按钮提示去跑 `tools/scene-template/run_m2_demo.sh`（符合「viewer 不重造合并」）。
- 模板合并 CLI 已绿（M2）：`merge_scene_template.mjs` 的 `mergeSceneTemplate` / `duplicateModel`；`prepare_preview_scene.mjs` 只派生预览输入（隐藏缺失 mesh、可选注入产品相机）；`smoke.mjs` + `run_m2_demo.sh`。
- 相机切换：`ViewControls.tsx` 的 `CameraControls` 只能切 glTF 里自带的相机 + Orbit，**没有** scene JSON 的 `views`（正视图 / 特写）预设。`editor-parity.md` 已写明：viewer 没有 named view presets。
- 导出入口：`Toolbar.tsx`「Export」打开 `ExportDialog.tsx`，本机再跑路径追踪出 PNG，或下载当前视口。**没有**「提交渲染 / 云端成片」动作，也没有「实时查看 / 高质量预览」切换。

**缺什么**

- **没有光栅实时查看模式**，没有合批 / 自适应画质 / `compileAsync` 后再揭开画面的实时路径。仓库内未使用 Three `compileAsync`；`fromTHREE.ts` 还明确 BatchedMesh 不能作为路径追踪输入。
- 没有与 `previewEnabled` 分开的 `viewMode`（或同等命名）。无法「默认实时查看，一键切高质量预览并继承状态」。
- **状态同步的根缺口**：三层要共用同一份 scene JSON + asset map，但 viewer **不能加载** `scene.json`。现有 scene JSON 只在 `stage_render` 与双轨里用（摸底文 §5.3.3 已指出）。Viewer 状态是「一份 Three 场景 + `store` 设置」，和预览 / 成片轨道的 scene 快照不是同一份源。
- 套模板后不能在 viewer 实时查看里立刻看到合并结果：面板不调用合并，也不把 `m2-merged.json` 载入画布。M2 预览是头less 出一张 PNG。
- UI 文案还没有「实时查看 / 高质量预览 / 提交渲染」三分法；视口 Export 若被理解成成片，会破边界。
- 样例表与 M2 夹具的 `replace_id` 不是同一条：`scene-templates.sample.json` id 5（冰箱厨房）是 `ccdaa114-…`（官方 `RF_Kitchen_0302_Scene`）；`run_m2_demo.sh` 用的是备份导入场景占位 `BingXiang` = `c83a2f4a-…`。列表点选不能直接驱动现有 demo。

### F3 模板烘焙光 — 完全没有（本轮先不做，但缺口要记清）

- 模板目录没有 lightmap / UV2 / IBL 立方体约定，viewer 实时路径也不读烘焙贴图。
- 合并层目前不会「带过」烘焙字段（也正确：设计要求烘焙逻辑不要写进占位替换）。
- 已知合并缺口仍在（`tools/scene-template/README.md` TODO，摸底 §2.3）：`meshes[*].url` 不改写；`views[*].model_group_visibility` 不 remap。M2/M4 还记录：厨房模板 GLB 不在本地备份，`prepare_preview_scene.mjs` 把缺失 mesh 隐藏，预览里只有产品、没有厨房壳——**没有壳就无法验烘焙**。
- 模板 `cam_01` 朝向与冰箱正面不对齐，预览靠注入产品相机绕过（`prepare_preview_scene.mjs`、`M2-PROGRESS.md`）。

### F4 色彩与材质对齐 — 双轨有身份表，三层色调未对齐

- Viewer / 云预览默认 AgX（`store.ts` `toneMapping: 'agx'`；`worker.py` 默认 `agx`）。
- **成片轨道不是 AgX**：`blender_inner.py` L610 `scene.view_settings.view_transform = "Standard"`。若实时再跟 viewer AgX，成片留 Standard，就已经是两套曲线；设计要求「不要引入第三套」，但「成片要不要改成 AgX」文中未拍板。
- 成片特殊材质只在 `blender_inner.py`（CAD 调试塑料、门边粉末、近白抽屉、玻璃）。预览轨 `stage_render.rs` 对 Glass master 也有 transmission 处理（约 L709），两边特例并不完全同一张表。
- 没有「按契约材质名」的实时着色补丁层，也没有 2–3 个样件的三层对照图目录（现有 `preview.png` / `final.png` / `compare.png` 是双轨冰箱对照，不是三层、也不是为本轮 F4 固定的金属 / 玻璃样张）。

### F5 实时档位 — 没有

- `RenderPanel.tsx` 的采样 / 反弹 / 分辨率 / 降噪是**路径追踪**参数，不是实时查看的「流畅 / 标准」档。
- 没有针对「模板空间 + 产品」的实时帧时间记录。

### Living Room / 房间资产（保持现状，不要改）

- `model-presets.json` L511 / L524：`Living Room`、`Living Room 2`，`category: "research"`。
- `researchModelPresets.ts` / `publicModelPresets.ts` / `presets.ts`：研究场景与公开示例分开；`ExamplesBrowser` 当示例加载。
- `ModelPreset` 无 `replace_id`。加载路径是整包 glTF（`ViewerEngine.loadPreset`），没有占位换品。
- **不要**把可影 template 行写入 `model-presets.json`。场景模板只走右栏「场景模板」。

---

## 3. 建议改动文件清单

只列建议，确认前不动手。尽量具体到文件。

### F1（第 1 步）新增

| 建议路径 | 为何 | 不做什么 |
| --- | --- | --- |
| `tools/import-contract/README.md` + 官方导出预设（建议 `export_glb_preset.py`，或同等的 Blender 导出参数表） | 把「必须保留 / 允许 / 禁止」写成可执行预设，给转换脚本和成片侧再导出共用 | 不把预设做成独立展厅导出；默认路径不加 `flatten` / `prune` / `palette` |
| `tools/import-contract/validate_glb.*` | 检查网格 / 节点名、材质名、`Pivot` 节点、相机名、占位 / `replace_id` 节点；失败要非零退出并打日志 | 不改路径追踪内核 |
| `tools/import-contract/fixtures/` | 好样件（命名材质 + 枢轴，冰箱 / 洗衣机或减速器）+ 一份故意破坏的坏 GLB（去名 / 拍平枢轴 / palette） | **不用 Living Room** |

### F1 修改

| 文件 | 为何 | 不做什么 |
| --- | --- | --- |
| `tools/import-smoke/convert_fbx_to_glb.sh`、`convert_stp_to_glb.sh`、`tools/import-smoke/smoke.sh` | 改走官方预设，转完跑校验；STP 缺材质 / 单位问题要失败或显式警告，不能静默出「能打开但绑不上材质」的 GLB | 不在 viewer 里引入 FBX / OCCT |
| `tools/cloud-relay.py` | 远程转换同样走预设 + 校验 | 不把 8787 改成成片 |
| `viewer/src/engine/loadModel.ts`、`ViewerEngine.ts` `loadFiles` | 导入后跑契约检查，toast / 日志报告缺名、无枢轴、仅默认材质等 | 不在这里做模板合并 |
| `docs/technical/import-greenpath-m3.md` | 补上契约门禁与样件证据路径 | — |

### F2（第 2 步）新增 / 修改

| 文件 | 为何 | 不做什么 |
| --- | --- | --- |
| `viewer/src/store.ts` | 新增与 `previewEnabled` **分名**的查看模式（例如 `viewMode: 'realtime' \| 'qualityPreview'`），默认 `'realtime'`；`previewEnabled` 仍只表示路径追踪交互低分预览 | 不复用 `previewEnabled` 当实时查看开关 |
| `viewer/src/engine/ViewerEngine.ts`、`viewer/src/components/Viewport.tsx` | 实时查看：对**已加载** Three 场景做光栅绘制（合批、自适应、`compileAsync` 后再揭开）；高质量预览：现有路径追踪。切换时继承相机、显隐、材质 | 不另开只读演示站；不 `export` 独立展厅 HTML；不把实时画面标成「效果图 / 成片」 |
| 新的模式切换 UI（建议挂 `Toolbar` 或 `Viewport` 底栏，文案：「实时查看 / 高质量预览」；提交成片单独入口） | 三分法必须可见 | 不要把 `ExportDialog` 的视口 PNG 写成成片 |
| `viewer/src/components/ExportDialog.tsx` / 提交渲染入口 | 「提交渲染」接到本机 `run_blender_final.py`，传同一份 scene.json + asset map + 当前相机/视图；数据形态与双轨成片一致，方便以后接云端 | 不要再跑一遍 viewer 路径追踪冒充成片；不要把 8787 预览工人当成成片；云端 Blender 不是 F1/F2 验收门槛 |
| `viewer/src/components/SceneTemplatePanel.tsx` | 选模板后**调用**已有 `tools/scene-template/merge_scene_template.mjs`（或 `import { mergeSceneTemplate }`），把合并结果交给加载入口；先出现在实时查看 | **禁止**把 `duplicateModel` / 占位删除逻辑抄进面板 |
| 新的只读 scene.json + asset map 加载适配（走拍板 A） | 映射到已有 Three 场景、相机、显隐、材质；资产按 map 里的 GLB 加载，使三层共用同一份状态 | 不以「先导出整场景 GLB 再 `loadFiles`」当主契约；不在 viewer 里重建合并或第二套格式 |
| `viewer/src/components/ViewControls.tsx`（或场景管理薄入口） | 消费合并结果里的 `views`（正视图 / 特写），切相机；实时与高质量预览共用 | 不要把场景管理做成模板入口；不要用 Living Room preset 冒充视图 |

### F3 / F4 / F5（F1+F2 绿了再做）

| 范围 | 建议落点 | 不做什么 |
| --- | --- | --- |
| F3 模板烘焙资产约定 | 模板目录字段 + 实时查看读 UV2 / IBL；`merge_scene_template.mjs` **只带字段、不烘焙**。等官方厨房壳补到本地再做 | 不把烘焙写进占位替换；不烤产品材质；不用 lightmap 替成片灯；不假装本机已有官方壳，不擅自拉全量官方桶 |
| F4 | 实时默认 AgX（已有）；高质量预览保持 AgX；成片维持 Standard，不改 `blender_inner.py` 的 `view_transform`。验收：色相不乱跳、允许实时更亮，不是三层套同一条曲线 | 不把实时补丁带进 `blender_inner.py` / `stage_render.rs`；成片改 AgX 须另独拍板并重做金样 |
| F5 | 实时档位设置与帧时间日志，与 `RenderPanel` 的 spp / 降噪隔离 | 切档不丢材质名 / 相机；不用 Living Room 充数 |

### 明确不要改的文件（本轮）

- `viewer/src/engine/model-presets.json`、`publicModelPresets.ts`、`researchModelPresets.ts`：Living Room 保持房间资产。
- `tools/scene-template/merge_scene_template.mjs` 的合并语义不重写；本轮**只允许**补 `meshes[*].url` 改写、`views` remap、以及保留 F2 切视图所需的产品相机。修复不进 viewer。其余缺口仍单独立项。
- 路径追踪内核（`src/renderer/**`）：F1 不先改这里。

---

## 4. 建议实施顺序

与设计第 5 节一致，A 绿了再上 B。编码仍走 DSH headless + Magpie `kiro/claude-sonnet-5.5`，禁止 Claude Code；Sonnet 全机硬并发 1。

1. **F1 导入导出契约**：官方预设 + 导入校验 + 转换脚本改走预设。完成标准：设计第 4 节 F1 验收（好样件名字还在；坏 GLB 被抓住；按名能绑材质）。
2. **F2 实时查看与高质量预览切换，状态必须同步**。完成标准：同一合并场景切视图再切模式，相机 / 材质一致；约 2 秒可转；文案三分法；提交成片仍走 Blender。
3. **F3** 选一个已有 `replace_id`、且壳资产在本地的真模板做烘焙光（厨房 GLB 若仍缺失，先避开并在验收材料写明）。
4. **F4 + F5**：三层对照图 + 实时档位帧时间。

---

## 5. 拍板后的执行口径（原待确认项已收口）

见上文第 0 节。开写后按该 7 点执行，不再把它们当未决问题。补充执行注意：

- F1 夹具：带命名材质和 Pivot 的好样件（优先冰箱单品或现有工业减速器），**不用 Living Room**。STP 转换后必须跑契约校验，缺材质/无单位换算要失败或显式警告；STP 补材质和 mm→m 另列缺口，不挡主路径。
- F2 夹具：本机 `tools/scene-template/fixtures/real/template-fridge-kitchen.json` + 冰箱单品，`replace_id` `c83a2f4a-…`。验收写明官方壳缺失、厨房 mesh 会被隐藏，本轮只验状态同步和模式切换。
- 面板目录里的官方冰箱厨房 `ccdaa114-…` 标为不可验收，不要改成 M2 ID。
- F3/F5 等官方壳 `RF_Kitchen_0302_Scene` 补到本地后再做，不要擅自拉全量官方桶。

## 6. 第 6 节验收证据预案

POC 交验收时按设计第 6 节给**命令、日志、截图或对照图**，不要只写「已完成」。建议统一落到（创建但不预先提交）：

`docs/prd/evidence/fusion/`

| 清单项 | 将提供的证据 | 建议落点 / 命令（落地后填实际） |
| --- | --- | --- |
| 1. 边界仍在 | 说明：三层仍在；成片命令仍是 Blender；无独立展厅交付物；合并仍只在 `tools/scene-template`，viewer 只调用不重造；Living Room 仍在 `model-presets.json` 研究示例，不在场景模板列表 | `docs/prd/evidence/fusion/00-boundary.md`（附相关路径与截图：模式文案、模板栏、Examples 里的 Living Room） |
| 2. F1 | 好样件：优化导出后节点 / 材质 / Pivot / 相机名仍在；按名绑材质；实时与高质量预览同一套材质。坏 GLB：校验非零退出，日志写明破坏点。不得出现「基色洗白且无报错」 | 命令：官方预设导出 + `validate_glb`（好 / 坏各一次）。日志：`docs/prd/evidence/fusion/f1/validate-good.log`、`validate-bad.log`。名册 dump 与截图：`f1/names-before.json`、`names-after.json`、绑材质截图 |
| 3. F2 | 同一已合并场景：实时下切正视图 / 特写，再切高质量预览，相机与材质一致；开发机可转圈时间（目标约 2 s，超时写原因）；UI 文案截图证明未把实时图叫成片 | 命令：合并（`node tools/scene-template/merge_scene_template.mjs …`）→ 载入 viewer；切模式前后截图 `f2/realtime-front.png`、`realtime-closeup.png`、`quality-front.png`、`quality-closeup.png`；交互计时日志 `f2/interact-timing.log` |
| 4. F3（若已做） | 同模板同产品：无烘焙 vs 有烘焙，实时空间光感不同；换品后壳光仍在、产品不被烤色；高质量预览 / 成片仍走物理灯 | `f3/realtime-nobake.png`、`realtime-bake.png`、换品后壳光、`quality.png`、`final.png`；注明未用 lightmap 作为 Cycles 光源 |
| 5. F4（若已做） | 2–3 个材质（含金属、玻璃）三层并排，色相不乱跳 | `f4/compare-metal.png`、`compare-glass.png`（实时 \| 预览 \| 成片） |
| 6. 已知模板缺口 | 若 url / views remap 未修：写明避开了哪套模板、为什么；若已修：给修前 / 修后或测试命令 | `docs/prd/evidence/fusion/00-template-gaps.md` |

预览 / 成片对照可复用现有双轨入口（不要另写一套语义）：

```bash
python3 tools/dual-track/run_dual_track.py both \
  --scene <merged-or-preview-scene.json> \
  --asset-map <assets.json> \
  --preview-out docs/prd/evidence/fusion/f2/quality.png \
  --final-out docs/prd/evidence/fusion/f2/final.png \
  --compare-out docs/prd/evidence/fusion/f2/compare.png
```

云端 8787 若出现在证据里，只能标为高质量预览，不能标成片。

---

## 附录：本轮对照过的主要路径

- 设计 / 需求：`docs/prd/Blender-Web-3D与MuTracer融合设计.md`，`docs/prd/可影2.0-需求说明.md`
- 双轨：`docs/technical/dual-track-render.md`，`tools/dual-track/README.md`，`tools/dual-track/stage_semantics.md`，`tools/dual-track/blender/blender_inner.py`，`run_blender_final.py`，`run_dual_track.py`
- 模板：`tools/scene-template/README.md`，`merge_scene_template.mjs`，`prepare_preview_scene.mjs`，`run_m2_demo.sh`，`M2-PROGRESS.md`，`docs/technical/scene-template-fusion-scout.md`
- Viewer：`SceneTemplatePanel.tsx`，`Inspector.tsx`，`Viewport.tsx`，`Toolbar.tsx`，`ExportDialog.tsx`，`RenderPanel.tsx`，`DebugOverlay.tsx`，`ViewControls.tsx`，`store.ts`，`ViewerEngine.ts`，`loadModel.ts`，`droppedFiles.ts`，`scene-templates.sample.json`，`model-presets.json`
- 导入：`tools/import-smoke/*`，`docs/technical/import-greenpath-m3.md`，`tools/cloud-relay.py`
- 云预览：`tools/cloud-service/README.md`，`api.py`，`worker.py`
- 其它：`docs/technical/editor-parity.md`，`docs/technical/m4-e2e-gap.md`
