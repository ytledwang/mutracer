# Import contract（F1）：名字就是契约

导入和再导出时必须保留网格 / 节点名、源文件材质名、名称含 `Pivot` 的转动节点、相机名、占位或 `replace_id` 节点。允许 Draco / meshopt / 纹理压缩与静态合批，但合批不得越过动画或枢轴祖先，不得把不同材质合并到丢掉名字。

默认路径禁止 `flatten` / `prune` / `palette` / `gltfpack`。官方厨房壳 `RF_Kitchen_0302_Scene`（`ccdaa114-…`）不在本机，本目录夹具是合成的冰箱形产品样件，不是官方壳，也不是 Living Room。

## 文件

- `export_glb_preset.py` — Blender 官方导出预设。转换脚本和 `tools/cloud-relay.py` 共用。
- `validate_glb.py` — 契约校验，失败非零退出。
- `fixtures/good-named-pivot.glb` / `fixtures/bad-flattened-palette.glb` — 好 / 坏夹具。
- `build_good_fixture.py` / `make_bad_glb.py` — 生成夹具。

## 命令

```bash
# 官方预设导出（FBX / STL / GLB）
blender --background --python tools/import-contract/export_glb_preset.py -- \
  --input in.fbx --output out.glb --importer fbx

# 好样件
python3 tools/import-contract/validate_glb.py \
  tools/import-contract/fixtures/good-named-pivot.glb \
  --require-pivot --require-camera \
  --expect-pivot Door_Pivot --placeholder f1-named-pivot-placeholder

# 坏样件（应失败）
python3 tools/import-contract/validate_glb.py \
  tools/import-contract/fixtures/bad-flattened-palette.glb \
  --require-pivot --expect-pivot Door_Pivot
```

`convert_fbx_to_glb.sh` 与 `convert_stp_to_glb.sh` 已改走该预设并在转换后校验。STP 缺材质或未做 mm→m 会失败或显式警告，失败产物改名为 `*.rejected.glb`，不会静默留下坏文件。把 STP 补材质和 mm→m 做成可卖转换是另列缺口，不挡 F1 主路径。

## Viewer

打开 viewer 后拖入 `.glb`：`loadModel.ts` 会跑与上面同一套结构规则，`ViewerEngine` 用 toast 和控制台 `[import-contract]` 报告缺名、palette 合并、仅默认材质、无 Pivot 等。不要在 viewer 里引入 FBX / OCCT。

```bash
npm run viewer
# 然后拖入 tools/import-contract/fixtures/good-named-pivot.glb 或 bad-flattened-palette.glb
npm run test:viewer -- viewer/tests/importContract.test.ts
```
