# scene-template：可影 CreateScene 合并薄层

把可影（my-stage-hk）「场景模板 + 单品 → 新场景」的合并语义做成离线 CLI。

**合并语义属可影。** 本目录是对可影代码的移植，不是新设计，也不在 viewer 里重造模板语义（占位替换、`replace_id`、视图、材质组状态）。viewer 只应消费合并后的 `scene.json`。以可影为准，两边有出入时改这里。

移植来源（只读）：

- `app/project/[id]/layout.tsx` 的 `handleCreateScene`（约 L378-507）
- `components/editor/panel/asset/handler/duplicate.ts` 的 `duplicateModel`

## 用法

零依赖，Node 18+。

```bash
node tools/scene-template/merge_scene_template.mjs \
  --template <tpl.json> --product <product.json> \
  --replace-id <uuid> --out <out.json>
```

- `--template`：模板 `scene.json`（可影 `template.data_bucket_url` 下）
- `--product`：单品 `scene.json`（`my_asset`，`scene_category=single`）
- `--replace-id`：模板表的 `replace_id`，即模板中占位 group 的 id
- `--out`：输出合并后的 scene JSON（目录不存在会创建）

也可作为模块使用：`import { mergeSceneTemplate, duplicateModel } from './merge_scene_template.mjs'`。`mergeSceneTemplate({ sceneTemplateData, singleSceneData, replaceId })` 返回 `{ scene, newModelId, replaceIdParent }`，不修改入参。

## 合并规则（与可影一致）

1. 单品 `models[ROOT]` 与占位 group 浅合并：占位属性（name、position、rotation_euler、scale、type 等）覆盖，`children` 保留单品自己的。
2. `duplicateModel`：单品整棵子树换新 uuid，所有 `children` 按映射改写，新根 `type='group'`。
3. 递归删除模板中 `replaceId` 及其后代。
4. 占位的父节点 `children` 去掉 `replaceId`，末尾追加新根 id。
5. `models / materials / textures / meshes / decals` 按 key 合并（产品覆盖同 key），`decals[ROOT].children` 两侧拼接。其余顶层字段（`lights / cameras / environments / views / scene_settings`）整体取自模板，产品里的不进入结果。

与可影的差异只在错误处理：缺 `replaceId`、占位不存在、找不到占位父节点时直接报错退出（可影对最后一种情况静默不挂载，产物会丢产品）。

## 烟雾测试

```bash
node tools/scene-template/smoke.mjs
```

用 CLI 跑两组 fixture 并断言上述不变量（占位子树已删、父 children 末尾为新根、变换继承占位、产品旧 id 不残留、无悬空 children、各表按 key 合并）：

| 组 | 模板 | 产品 | 输出 |
| --- | --- | --- | --- |
| synthetic | `fixtures/synthetic-template.json` | `fixtures/synthetic-product.json` | `out/merged-synthetic.json` |
| real | `fixtures/real/template-fridge-kitchen.json`（local-stack 备份 `customer_asset/08a5e3eb…`，占位 `BingXiang` = `c83a2f4a-0a3d-4494-8da9-37e6ca6943a7`） | `fixtures/real/product-3fbx-single.json`（`customer_asset/0ae9a833…`，`3.FBX-[单品渲染]`） | `out/merged-smoke.json` |

`real` 组的模板是备份里的「冰箱-厨房场景」样例导入场景，不是 `template` 表里的 `RF_Kitchen_0302_Scene`（该桶文件不在本地备份中），但占位 group 结构相同。其占位变换为单位变换，所以平移/旋转继承只由 synthetic 组（非单位变换）覆盖。

## TODO（可影已知缺口，本轮保持原样，见 `docs/technical/scene-template-fusion-scout.md` §2.3）

- `meshes[*].url` 不改写：可影 `CreateSingle` 会改写为 `<data_bucket_url>/<url>`，`CreateScene` 没有。产品 mesh 的相对 URL 合并后可能解析不到。
- `views[*].model_group_visibility` 不 remap：指向已删 `replaceId` 的条目会悬空，新根 id 不在任何视图里。
- 产品自带的相机、灯光、环境被丢弃，是否有意待可影确认。

以上应由可影确认修法后同步到这里。
