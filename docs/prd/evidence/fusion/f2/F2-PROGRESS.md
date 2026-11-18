# F2 进度 / 验收摘要

时间：2026-11-10 23:31–23:50 Asia/Shanghai。按要求在 Mac mini 仓库直接落地 F2，未跳到 F3/F4/F5，未 git add / commit / push。HEAD 仍为 `af527ef`。

## 做了什么

- Viewer 新增与 `previewEnabled` **分名**的 `viewMode: 'realtime' | 'qualityPreview'`（默认实时查看）。底栏三分法文案：**实时查看 / 高质量预览 / 提交渲染**。
- 实时查看：同一份已加载 Three 场景走 WebGL 光栅叠加层；高质量预览：现有 MuTracer 路径追踪。切换时不重载模型，继承相机 / 显隐 / 材质 / 合并结果。
- 拍板方案 A：只读 `scene.json` + asset map 适配（`loadSceneJson.ts`），不走「整场景 GLB → loadFiles」主契约。
- 场景模板面板：官方冰箱厨房 `ccdaa114-…` 标 **不可验收**（未改成 M2 ID）；「套用本机 M2 夹具」经 Vite `/api/f2/apply-m2` 调用现有 `merge_scene_template.mjs` + `prepare_preview_scene.mjs`，结果先进实时查看。
- `merge_scene_template.mjs` 仅补三处：`meshes[*].url` 改写、`views` remap、保留产品相机（并并入不冲突的产品视图）。灯光/环境仍取自模板。
- 「提交渲染」经 `/api/f2/submit-final` 接到本机 `tools/dual-track/blender/run_blender_final.py`（8787 未改）。本轮对 M2 预览 scene **真跑** spp=4 / 640×360，产物 `f2-final-spp4.png`（约 27 s，exit 0）。成片 view_transform 未改（仍 Standard）；实时/高质量仍 AgX。

夹具：模板 `tools/scene-template/fixtures/real/template-fridge-kitchen.json` + 冰箱单品 `tools/cloud-service/poc-out/fridge/assets/customer_asset/1d0db88a-…/scene.json`，`replace_id=c83a2f4a-0a3d-4494-8da9-37e6ca6943a7`。官方壳 `RF_Kitchen_0302` / `ccdaa114-…` 不在本机；合并预览隐藏缺失厨房 mesh（约 87），本轮只验状态同步与模式切换，不是完整厨房空间光感。

## 命令与退出码

```bash
# 合并（已打补丁的 merge）
node tools/scene-template/merge_scene_template.mjs \
  --template tools/scene-template/fixtures/real/template-fridge-kitchen.json \
  --product tools/cloud-service/poc-out/fridge/assets/customer_asset/1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a/scene.json \
  --replace-id c83a2f4a-0a3d-4494-8da9-37e6ca6943a7 \
  --out docs/prd/evidence/fusion/f2/m2-merged.json

node tools/scene-template/prepare_preview_scene.mjs \
  docs/prd/evidence/fusion/f2/m2-merged.json \
  tools/cloud-service/poc-out/fridge/stage-fridge-assets.json \
  docs/prd/evidence/fusion/f2/m2-preview-scene.json \
  tools/cloud-service/poc-out/fridge/assets/customer_asset/1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a/scene.json \
  298cfe60-923d-44fb-a0d1-f2206b9a48e1 \
  1c4a3883-8668-4c16-a10e-0b7c24272279

# 成片挂钩（本机 Blender 5.1.1）
python3 tools/dual-track/blender/run_blender_final.py \
  --scene docs/prd/evidence/fusion/f2/m2-preview-scene.json \
  --asset-map docs/prd/evidence/fusion/f2/stage-fridge-assets.json \
  --view 1c4a3883-8668-4c16-a10e-0b7c24272279 \
  --out docs/prd/evidence/fusion/f2/f2-final-spp4.png \
  --width 640 --height 360 --spp 4 --denoise 0
```

| 检查 | 结果 |
| --- | --- |
| `node tools/scene-template/smoke.mjs` | 通过（synthetic + real） |
| 合并日志 | `merge.log`；`merge-summary.json`：535 models，11 cameras，5 views；preview 隐藏 87 缺失 mesh |
| `run_blender_final.py` spp=4 | exit 0；`f2-final-spp4.png`；日志 `submit-final-run.log`；另有入参 dry-run 记录 `submit-final-dry-run.log` |
| `npm run test:viewer` | 47 files / **404 passed** |
| `npm run typecheck:viewer` | 通过 |

## 截图（含 F1 残留补拍）

Playwright 对 `npx vite --config viewer/vite.config.ts --host 127.0.0.1 --port 3012`：

| 文件 | 内容 |
| --- | --- |
| `f1-named-materials-realtime.png` | 加载 `good-named-pivot.glb`，实时查看 |
| `f1-named-materials-quality.png` | 同模型切高质量预览 |
| `f1-bad-contract-toast.png` | 加载 `bad-flattened-palette.glb` 的契约错误 toast |
| `f2-catalog-official-unavailable.png` | 官方厨房条目标「不可验收」 |
| `f2-realtime-after-template.png` | 套 M2 后实时查看 |
| `f2-quality-after-template.png` / `f2-mode-labels.png` | 模式切换与三分法文案 |
| `f2-final-spp4.png` | 本机成片挂钩真跑产物 |

说明：Chromium headless 下实时 WebGL 曾触发 PMREM/envMap shader 报错；已改为实时路径临时关闭 `scene.environment` 并用半球/方向光填充。高质量预览在 headless 中出现过 AOV pipeline 报错，真机 GPU 路径追踪仍是主验收面。脚本：`screenshots.mjs`，里程碑：`screenshots.log`。

## 未做 / 缺口

- 官方壳仍不在本机 → F3/F5 仍等壳；本轮厨房空间光感不可验收。
- 未接云端 Blender job；8787 仍只做预览。
- 实时查看尚未做合批 / `compileAsync` / F5 档位（属 F5）。
- 未提交任何文件；F1 与 `docs/prd` 其它脏文件保持未提交。
