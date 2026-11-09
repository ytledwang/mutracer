# 场景模板融合摸底（scene_template / replace_id）

只读调研，不含实现。可影仓指 `/Users/wangjianzheng/Project/HG/my-stage-hk`（下称“可影”），MuTracer 指本仓。可影路径均相对其根目录，行号取自调研时的工作区（该目录不是 git 仓库，无提交号可引）。

## 1. 背景与边界

- 可影的“场景模板”是**场景 JSON（`Scene`）层面的合并语义**：模板里有一个占位 group（`replace_id`），用户产品场景替换它，其余灯光、相机、环境、视图随模板保留。
- MuTracer 是渲染核心加 Three.js 派生的只读场景树。`docs/technical/editor-parity.md` 已写明：渲染场景只有 mesh、解析光源和背景，没有场景存储，场景 JSON 的 models/groups/views 语义不在 viewer 里。
- 边界：**不在 MuTracer 里重造模板语义**（占位替换、`replace_id`、`views`、材质组状态）。模板合并保持在可影侧（或其导出的 `scene.json`）完成。MuTracer 只消费合并后的结果：GLB 加资产映射，或双轨渲染已在用的 scene JSON（`tools/dual-track/stage_semantics.md`，`native/host/src/bin/stage_render.rs`）。
- viewer 里的“场景模板栏”应是一个入口：选模板、选产品、调用可影侧合并、把结果交给现有加载入口。它不重新实现合并。

## 2. 可影合并入口

### 2.1 文件与符号

| 作用 | 文件 | 符号 / 位置 |
| --- | --- | --- |
| 模板表结构 | `local-stack/supabase/migrations/0001_schema.sql` | `public.template`（约 L121-131）：`id, name, type, preview, data_bucket_url, replace_id, project_id`。`type` 取 `single_template` 或 `scene_template` |
| 类型 | `types/asset.ts` | `enum TemplateEnum { Single='single_template', Scene='scene_template' }`；`interface TemplateAsset extends BasicAsset { type; replace_id?: string }`；`enum SceneCategory { Single, Scene }`；`MyAsset.scene_category` |
| 场景类型 | `types/stage.ts` | `ROOT_ENTITY_ID`（L15，全零 UUID）；`interface Scene`（L498：`models, cameras, lights, materials, meshes, scene_settings, textures, environments, decals, views`）；`View`（L480：`active_camera, active_environment, material_group_states, light_group_visibility, model_group_visibility, decal_group_visibility`）；`GroupEntity / RootEntity / MeshEntity / DecalRoot` |
| 拉取模板列表 | `hooks/asset.ts` | `useTemplateAssets({ type })`（L111），查 `template` 表，按 `type` 过滤 |
| 表名与桶 | `utils/supabase/constant.ts` | `TemplateTableName='template'`；`MyAssetBucketId='customer_asset'`；`MyAssetTableName='my_asset'` |
| 模板列表 UI | `components/project/template-list.tsx`、`components/workspace/template-card.tsx` | `TemplateList`、`TemplateCard` |
| 读取 scene.json | `utils/http.ts` | `fetchBucketSceneData(bucketUrl)`（L54）→ `fetchSceneData(folder, bucketId)`，读 `<bucket>/<folder>/scene.json` |
| ID 重写 | `components/editor/panel/asset/handler/duplicate.ts` | `duplicateModel(json, modelId)`（L68）：递归为 group/root 子树生成新 uuid、更新 `children`，返回 `{ modelData, newModelId }`。同文件有 `duplicateMaterial / duplicateEnv / duplicateLight` |
| **场景模板合并** | `app/project/[id]/layout.tsx` | `CreateScene`（L348）内的 `handleCreateScene`（L378-507）。入口按钮文案 `Scene Template` |
| 产品模板（对照） | 同上 | `CreateSingle`（L61）内的 `handleCreateSingle`（L95-），用 `single_template`，没有 `replace_id` |
| 样例数据 | `local-stack/backup/20261024-202844/tables/template.json`、`local-stack/supabase/seed.sql`（DefaultScene） | 见 2.3 |

### 2.2 `handleCreateScene` 合并流程（`scene_template`）

输入：用户选的“单品场景”（`MyAsset`，`scene_category=single`）和 `TemplateAsset`（`type=scene_template`，必须有 `replace_id`）。

1. 用 `fetchBucketSceneData` 读单品场景 `singleSceneData` 和模板 `sceneTemplateData`。模板缺 `replace_id` 时直接 `onCreateError`（L398）。
2. 取占位：`replacedGroup = sceneTemplateData.models[replaceId]`。
3. 把单品 `models[ROOT_ENTITY_ID]` 与占位 group 浅合并：占位的属性（名称、位置、旋转、缩放等变换）覆盖到单品根上，`children` 保留单品自己的（L408-413）。这一步让产品继承占位的摆放。
4. `duplicateModel(singleSceneData, ROOT_ENTITY_ID)` 把单品整棵子树改成新 uuid，根变为 `type='group'`，得到 `newModelId`。
5. **删占位**：递归 `deleteEntity(replaceId)` 删除模板 `models[replaceId]` 及其全部后代（L421-432）。
6. **塞产品**：找到 `children` 含 `replaceId` 的父节点，从其 `children` 去掉 `replaceId`，追加 `newModelId`（L434-446）。
7. **按 key 合并**：`{...sceneTemplateData, models/materials/textures/meshes/decals: {...模板, ...产品}}`。`decals[ROOT_ENTITY_ID].children` 为模板与产品两边拼接。
8. 上传 `customer_asset/<newSceneId>/scene.json`，插入 `my_asset`（`type='scene'`, `scene_category=SceneCategory.Scene`, `data_bucket_url=customer_asset/<newSceneId>`）。

### 2.3 灯光 / 相机 / 环境 / 视图如何随模板

合并结果以 `...sceneTemplateData` 为底，只有 `models / materials / textures / meshes / decals` 做了“模板 + 产品”并集。其余顶层字段**整体来自模板，产品场景里的对应内容不进入结果**：

- `lights`、`cameras`、`environments`、`views`、`scene_settings`、`version`、`geometry_graphs`：全部取自模板。
- `views` 里的 `active_camera / active_environment / light_group_visibility / material_group_states / model_group_visibility` 引用的是模板内的 id，所以视图随模板。

已观察到的缺口（只读判断，未改代码）：

- `views[*].model_group_visibility` 等不会被改写。引用 `replaceId` 的条目会指向已删除的 id，`newModelId` 不在任何视图的可见性表里。
- `CreateSingle` 会把 `meshes[*].url` 改写为 `<data_bucket_url>/<url>`（L109-124），`CreateScene` 没有这一步。产品 mesh 的相对 URL 在合并后场景中可能无法解析，需在可影侧确认。
- 产品场景自带的相机、灯光、环境被丢弃，属有意还是遗漏，无注释说明。

### 2.4 样例数据

- 备份 `template.json` 中 `scene_template` 共 4 条，其中 `id 2/4/5` 有 `replace_id`（`DefaultScene`、`ACS_Bedroom_0302_Scene`、`RF_Kitchen_0302_Scene`），`id 12`（`Scene_7_WH_2cam`，路径在 `good_templates/`）`replace_id` 为空，按 L398 的判断会合并失败。
- `seed.sql` 的 `DefaultScene` 插入没有 `replace_id` 列，本地栈里直接用它做场景模板会失败。
- 备份中 `single_template` 的 `replace_id` 均为空，符合预期。

## 3. MuTracer 挂载建议（场景模板栏）

现有 UI 结构（`viewer/src/App.tsx`）：`Toolbar` → `<main.workspace>`，其中左 `SceneTree`、中 `Viewport`、可选浏览面板（`TextureBrowser` 或 `ExamplesPanel`）、右 `Inspector`、最右 `InspectorRail`（64px 竖向 tab 条）。布局由 `viewer/src/styles/app.css` 的 `.workspace[data-left][data-right][data-browse]` 网格列控制（L145-149）。

| 文件 | 符号 | 说明 |
| --- | --- | --- |
| `viewer/src/components/Inspector.tsx` | `TABS`、`PANELS`、`Inspector`、`InspectorRail` | 右侧栏 tab 都从 `TABS: {id,label,Icon}[]` 和 `PANELS: Record<InspectorTab, ...>` 推出。当前 4 个：`environment`(Lighting) / `material` / `camera` / `render` |
| `viewer/src/store.ts` | `type InspectorTab`（L272）、`ViewerState['ui']`（L302）、`setUi` | `ui.tab` 为持久化字段（`UI_KEY` 存储），移动端用 `mobileTab: InspectorTab \| 'scene'` |
| `viewer/src/App.tsx` | 数字键 `/^[1-4]$/` → `TABS[n-1]`（L65） | 新增 tab 后快捷键范围要同步 |
| `viewer/src/components/panels/` | `EnvironmentPanel / MaterialPanel / CameraPanel / RenderPanel` | 新面板放此目录，组件名建议 `SceneTemplatePanel.tsx` |

建议：

1. **首选**：新增右栏 tab `scene-template`（标签“场景模板”），做法是扩展 `InspectorTab`、`TABS`、`PANELS`，面板为 `SceneTemplatePanel`。这是改动最小的挂载点，桌面栏和移动 sheet 都自动带上。同步更新 `App.tsx` 的数字键范围。
2. 备选：沿用 `ExamplesBrowser.tsx` 的 `ExamplesMenu / ExamplesPanel` 模式（Toolbar 弹出或固定为列），适合模板缩略图较多时。代价是要新增 `ui` 字段和 `data-browse` 网格列逻辑。
3. 面板只做：模板列表（来自可影 API）、选择产品、触发合并、拿到结果后调用 `ViewerEngine.loadFiles / loadModel`（见第 5 节）。不要在面板里实现占位替换。
4. `ui.tab` 默认值为 `'material'`，新增 tab 不应改默认值。

## 4. Living Room 降级说明

相关文件：

- `viewer/src/engine/model-presets.json`：全部示例条目。`research-living-room`（L510，`url` 指向 `gltf-research-scenes` 的 `living_room_extended.gltf`）和 `research-living-room-2`（L523）带 `"category": "research"`。
- `viewer/src/engine/researchModelPresets.ts`：`RESEARCH_MODEL_PRESETS`，按 `category==='research'` 过滤，并导出 `RESEARCH_SCENES_SOURCE`。
- `viewer/src/engine/publicModelPresets.ts`：`PUBLIC_MODEL_PRESETS`，取其余条目。
- `viewer/src/engine/presets.ts`：`ModelPreset` 接口，`MODEL_PRESETS = [...PUBLIC, ...RESEARCH]`。
- 使用方：`ExamplesBrowser.tsx`（`models` / `research` 两个集合）、`ViewerEngine.loadPreset`（L282）、`Viewport.tsx`、`native/viewer/src/examples.rs`（“glTF Research Scenes”）。

结论：Living Room 只是一份**第三方 glTF 房间资产的示例条目**，不是 `replace_id` 的业务入口：

- `ModelPreset` 只有 `id/name/url/license/camera/stage/renderSettings` 等展示与许可字段，没有占位、`replace_id`、产品 id、视图或模板类型。
- 加载路径是 `loadPreset → loadModelFromURL` 整体载入，场景被当作一个不可拆分的 glTF，没有“删占位、塞产品”的步骤。
- 所以它的角色只能降级为**房间/环境资产库**：可用作演示、对比渲染或将来作为外部“房间背景”素材，不能代表可影的 `scene_template`。
- 不要把可影的 `template` 行写进 `model-presets.json`，也不要给 `ModelPreset` 加 `replace_id`。那会把模板语义带进 MuTracer，违反第 1 节边界。

## 5. 导入链摸底（GLB / FBX / STP）

### 5.1 MuTracer（viewer）

| 环节 | 文件 | 符号 |
| --- | --- | --- |
| 文件选择 | `viewer/src/components/Toolbar.tsx`（L136、L157） | `onFiles` → `getEngine()?.loadFiles(toPathedFiles(list))`；`accept=".glb,.gltf,.fbx,.stp,.step,.pbrt,.gz,.ply,.bin,图片/hdr/exr..."`；`.fbx/.stp/.step` 只识别、不解析，提示先用 `tools/import-smoke/convert_*.sh` 转 GLB |
| 拖放 / 交接 | `viewer/src/components/Viewport.tsx`（L24、L53）、`viewer/src/engine/droppedFiles.ts` | `readDroppedItems`、`HANDOFF_HASH='open=files'`、`stashFiles / takeStashedFiles`；`isModelFile = /\.(glb\|gltf\|pbrt\|pbrt\.gz)$/i` |
| 引擎入口 | `viewer/src/engine/ViewerEngine.ts` | `loadFiles`（L306）、`loadUrl`（L300）、`loadModel(model: LoadedModel)`（L296）、`loadPreset`（L282） |
| 解析 | `viewer/src/engine/loadModel.ts` | `loadModelFromFiles`（L116，只找 `.glb`/`.gltf`/`.pbrt`）、`loadModelFromURL`（L51）、`loadModelFromSource`、`parseModelSource`（用 Three `GLTFLoader`，带 Draco 和 Meshopt） |
| 转 MuTracer 场景 | `src/util/fromTHREE.ts` | Three.js 场景转换 |

- GLB/glTF：已有，支持外部资源、内嵌 HDR 光照。
- FBX：**viewer 和库内都没有**加载器，也未在 `accept` 里。
- STP/STEP：**viewer 没有**。

### 5.2 STP / FBX 转换

| 位置 | 能力 |
| --- | --- |
| 可影 `local-stack/remote-server/scripts/stage-converter.py` | 轮询 `converter_task`。`DIRECT_FORMATS` 含 `.fbx .glb .gltf .obj .stl .ply .usd* .blend`，经 Blender 管线转为 `scene.json + models/*.glb`。`PIXYZ_FORMATS = {.x_t,.stp,.igs,.iges,.step}` 直接置 `failed`（需要 Windows Pixyz，Linux 版不支持）。`ARCHITECTURE-REMOTE.md` L82-83 同述 |
| 可影 `app/model/page.tsx` | 上传 `ACCEPTED_FILE_TYPES` 含 `.fbx`、`.stp`、`.glb`，表 `converter_task` |
| MuTracer `tools/cloud-relay.py`（L166 起） | 远程流程：`.step/.stp` → `gmsh -3 ... -format stl` → Blender 导入 STL → 导出 GLB → 远程 Blender 管线（`pipeline_script`）→ 取回 `scene.json + models/*.glb + assets.json`；另支持 `.stl/.glb/.gltf`。**不支持 `.fbx`**（L184 报错） |
| MuTracer `tools/dual-track/`、`tools/cloud-service/` | 消费 scene JSON 与 asset map 渲染，不做格式转换 |

### 5.3 缺口

1. viewer 无 FBX 加载入口，也无 STP 入口。前者可经可影 Blender 管线先转 GLB，后者只有 MuTracer `cloud-relay.py` 里 gmsh → STL → GLB 的网格化路径（STL 是三角网格，丢失 CAD 拓扑、材质与装配层级）。
2. 可影本仓的 STP 直转路径被 Pixyz 依赖卡住，在无 Windows worker 时不可用。
3. viewer 没有“读 `scene.json` + 资产映射”的入口，现有 `scene.json` 只在 `tools/dual-track` 和 `stage_render` 里使用。因此可影合并结果要么先导出成 GLB，要么新增一个 loader，后者需要先单独评审。
4. `cloud-relay.py` 依赖 SSH 远程主机与 `gmsh/blender`，没有在 viewer 中暴露。

## 6. 11-11 下一步建议

1. **与可影确认合并产物形态**：由可影侧在合并后导出什么（合并后 `scene.json` 加 asset map，还是整场景 GLB）。该选择决定 viewer 要不要新增 loader，先定再动 UI。
2. **补齐 `replace_id` 数据与两处缺口**：确认 `Scene_7_WH_2cam` 与 `seed.sql` 的 `DefaultScene` 的 `replace_id`；确认 `CreateScene` 未改写 `meshes[*].url`、未更新 `views` 对 `replaceId` 引用，由可影决定修复，避免把缺陷带进 MuTracer 渲染。
3. **做一个最小的“场景模板” tab 原型**（只列模板和选产品，调用可影合并接口，结果走 `ViewerEngine.loadFiles`），挂在 `Inspector.tsx` 的 `TABS/PANELS`，同时更新 `App.tsx` 数字键。不接入 `model-presets.json`。
4. **决定 FBX 与 STP 的上游转换位置**：建议都在可影（或 `cloud-relay.py`）转为 GLB，viewer 保持只吃 GLB/glTF；不要在 viewer 内引入 FBX/OCCT 解析依赖。需要时再给 `cloud-relay.py` 补 `.fbx` 分支。
5. **用现成三个有 `replace_id` 的模板做端到端验证**：可影合并 → 导出 → viewer 载入 → 双轨 `tools/dual-track` 对照，记录相机、灯光、环境是否与可影预览一致，再决定是否需要在 viewer 中显示视图（相机）切换。

## 7. M1 落地

范围：右侧 Inspector 增加「场景模板」tab 和只读列表。不调用合并接口，不出图，不接 `model-presets.json`。

| 文件 | 改动 |
| --- | --- |
| `viewer/src/store.ts` | `InspectorTab` 增加 `'scene-templates'` |
| `viewer/src/components/Inspector.tsx` | `TABS` 增加「场景模板」（`Layers` 图标），`PANELS` 挂 `SceneTemplatePanel` |
| `viewer/src/components/SceneTemplatePanel.tsx` | 新建。列出名称、type、是否有 `replace_id`；缺 `replace_id` 的项标「不可用」。点选高亮，详情显示 `id` / `replace_id` / `data_bucket_url`。「合并预览（M2）」按钮 disabled |
| `viewer/src/engine/scene-templates.sample.json` | 新建。取自可影备份 `local-stack/backup/20261024-202844/tables/template.json`，只留 `type=scene_template` 的 4 项（id 2、4、5、12），字段为 `id/type/name/replace_id/data_bucket_url`。id 12 缺 `replace_id` |
| `viewer/src/App.tsx` | 数字键范围 `1-4` 改为 `1-5` |
| `viewer/src/styles/app.css` | 增加 `.tpl-*` 样式，沿用现有变量 |
| `docs/viewer-checklist.md` | 快捷键说明改为 1–5 |
