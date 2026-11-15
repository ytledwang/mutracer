# F1 进度 / 验收摘要

时间：2026-11-10 22:54–23:02 Asia/Shanghai。按 Bano 要求停用 DSH，由 MuTracer-POC 直接落地。未跳到 F2/F3。未 git add / commit / push，差距页和其他 `docs/prd/` 未提交。

## 做了什么

- 新增 `tools/import-contract/`：官方导出预设、`validate_glb.py`、合成好样件（命名材质 + Pivot + 相机 + 合成 replace_id）、故意破坏的坏 GLB。
- `convert_fbx_to_glb.sh` / `convert_stp_to_glb.sh` / `smoke.sh` 改走预设并校验。STP 失败会把产物改名为 `*.rejected.glb` 并非零退出。
- `tools/cloud-relay.py` 远程转换同样 scp 预设和校验；可用 `--allow-contract-failures`。本轮未对真实远程主机跑转换。8787 未改成成片。
- Viewer：`importContract.ts` 在导入后检查 glTF JSON，toast / `console.info('[import-contract]', …)` 报告问题。

夹具说明：官方厨房壳 `RF_Kitchen_0302_Scene`（`ccdaa114-…`）不在本机，未假装有壳，未拉官方桶。本机冰箱 poc-out GLB 没有 Pivot 节点，因此用 Blender 写了一份可提交的小合成样件，不是 Living Room。占位 id 是 `f1-named-pivot-placeholder`，不与官方 `ccdaa114-…` 或 M2 `c83a2f4a-…` 混用。

## 命令与退出码

官方预设导出好样件（已由 `build_good_fixture.py` 完成），再带 Draco 优化导出：

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  --python tools/import-contract/export_glb_preset.py -- \
  --input tools/import-contract/fixtures/good-named-pivot.glb \
  --output docs/prd/evidence/fusion/f1/good-optimized.glb \
  --importer glb --draco
```

| 检查 | 命令要点 | 退出码 | 日志 |
| --- | --- | --- | --- |
| 好样件 | `validate_glb.py fixtures/good-named-pivot.glb --require-pivot --require-camera --expect-pivot Door_Pivot --placeholder f1-named-pivot-placeholder` | 0 | `docs/prd/evidence/fusion/f1/validate-good.log` |
| Draco 优化后对照名册 | `validate_glb.py …/good-optimized.glb --baseline names-before.json` | 0 | `validate-optimized.log`；名册 `names-before.json` / `names-after.json`（节点、材质、Pivot、相机、replace_id 仍在） |
| 坏 GLB | `validate_glb.py fixtures/bad-flattened-palette.glb --require-pivot --expect-pivot Door_Pivot --placeholder …` | 1（11 error / 5 warning：去名、palette、Pivot/占位丢失） | `validate-bad.log` |
| STL 立方体 | 官方预设导出后校验 | 1（无材质） | `validate-cube.log` |
| STP `box.step` | `convert_stp_to_glb.sh` | 1；产物为 `tools/import-smoke/out/box-stp.rejected.glb`，原 `box-stp.glb` 已移走 | `validate-stp.log`（缺材质 ERROR + mm 未换算 WARN） |
| FBX `sample.fbx`（私有，不提交） | `convert_fbx_to_glb.sh` | 0 | `validate-fbx.log` |

Viewer 测试：`npm run test:viewer -- viewer/tests/importContract.test.ts viewer/tests/viewerModelLoading.test.ts` → 13 passed。`npm run typecheck:viewer` → 通过。

Viewer toast：本轮没有开浏览器截图。本地触发：`npm run viewer`，拖入 `good-named-pivot.glb`（通过，控制台 `[import-contract] ok`）或 `bad-flattened-palette.glb`（错误 toast：unnamed / palette / no Pivot）。

## 未做 / 缺口

- STP 补材质和 mm→m 仍不是可卖转换；F1 只把门加上，禁止静默出坏文件。
- 官方厨房壳仍不在本机；F3/F5 仍等壳到齐。
- 未在真实远程主机上跑 `cloud-relay.py convert`。
- 未做 F2（实时查看 / 高质量预览 / scene.json 适配 / merge 修 url 与 views）。
- 未提交任何文件。
