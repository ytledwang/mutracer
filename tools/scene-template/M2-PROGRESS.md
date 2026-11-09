# M2 进度：完成

选场景模板 → `replace_id` 合并 `scene.json` → MuTracer 本机预览。

## 一键

```bash
tools/scene-template/run_m2_demo.sh     # 末行：DONE_M2 merge=... preview=...
```

环境变量可覆盖 `TEMPLATE PRODUCT REPLACE_ID ASSET_MAP PRODUCT_VIEW MERGED_VIEW WIDTH HEIGHT SPP`。默认：冰箱厨房模板（`fixtures/real/template-fridge-kitchen.json`，`replace_id=c83a2f4a-…`）+ 冰箱单品 `1d0db88a-…`，640x360、16 spp，约 12 s。

## 产物（`out/`）

- `m2-merged.json`：合并后的 scene（535 models）。`smoke.mjs` 通过。
- `m2-preview-scene.json`：由 `prepare_preview_scene.mjs` 派生的预览输入。
- `m2-preview.png`：`run_dual_track.py preview` 出图，能看到产品替换到 `BingXiang` 占位处，产品带有开门体。

## 文件

- `merge_scene_template.mjs`、`smoke.mjs`：合并与烟雾（M2 前已有，未改）。
- `prepare_preview_scene.mjs`：预览专用的 scene 派生，见下。
- `run_m2_demo.sh`：merge → prepare → preview。
- `viewer/src/components/SceneTemplatePanel.tsx`：「合并预览」按钮改为指向脚本的提示，并带出选中模板的 `replace_id`。viewer 不执行合并。

## 已知限制

1. 预览图只有产品，没有厨房。模板 GLB（`official_asset/template/RF_Scene_Kitchen_2cam/…`，55 个 mesh）不在本地备份里（`DATA-STRATEGY.md`：未拉全量），`mutracer-render` 遇到缺失资源会直接报错。`prepare_preview_scene.mjs` 把 asset map 里没有的 mesh 节点设为 `is_visible=false`（87 个节点），并清空指向缺失贴图的材质引用（35 处）。`m2-merged.json` 本身不动。取得模板 GLB 后补进 asset map 即可，无需改脚本。
2. 合并结果的相机来自模板，模板 `cam_01` 在 +y 侧看向 -y，而冰箱正面朝 -y，拍到的是背面局部。预览时把单品视图 `298cfe60-…` 的相机注入 `m2-preview-scene.json`（仅预览派生物）。
3. 合并语义的已知缺口见 `README.md` 的 TODO（mesh url 不改写、views 的 `model_group_visibility` 不 remap）。
4. `SceneTemplatePanel` 的模板列表仍是 `scene-templates.sample.json`，未接真实数据。
