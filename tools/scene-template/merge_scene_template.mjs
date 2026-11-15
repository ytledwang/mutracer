#!/usr/bin/env node
// 可影 CreateScene 合并语义的移植薄层（零依赖，可离线运行）。
//
// 语义来源（只读参考，合并规则属可影，不在此重新设计）：
//   my-stage-hk/app/project/[id]/layout.tsx  handleCreateScene（约 L378-507）
//   my-stage-hk/components/editor/panel/asset/handler/duplicate.ts  duplicateModel
//
// 与可影的差异仅限于：不读写 Supabase、不修改入参（先 structuredClone）、
// 对可影会产生 undefined 崩溃或静默失败的输入抛出明确错误。
// F2 允许补三处：meshes[*].url 改写、views remap、保留产品相机（不重写合并语义）。

import { randomUUID } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT_ENTITY_ID = '00000000-0000-0000-0000-000000000000';

const isContainer = (entity) => entity?.type === 'group' || entity?.type === 'root';

/** Absolute-looking mesh URLs that CreateSingle would leave alone. */
const ABSOLUTE_URL = /^(?:https?:|\/\/|\/|customer_asset\/|official_asset\/)/i;

/**
 * Infer a product data_bucket_url for relative mesh URLs (CreateSingle-style prefix).
 * Prefer an explicit bucket, then scene_settings.data_bucket_url, then a shared customer_asset/… prefix.
 */
export function inferProductBucket(singleSceneData, explicitBucket) {
  if (explicitBucket) return String(explicitBucket).replace(/\/$/, '');
  const fromSettings = singleSceneData?.scene_settings?.data_bucket_url;
  if (fromSettings) return String(fromSettings).replace(/\/$/, '');
  const prefixes = new Set();
  for (const mesh of Object.values(singleSceneData?.meshes ?? {})) {
    const url = mesh?.url;
    if (typeof url !== 'string' || !url.includes('/')) continue;
    const parts = url.split('/');
    if (parts[0] === 'customer_asset' || parts[0] === 'official_asset') {
      if (parts.length >= 3) prefixes.add(parts.slice(0, 2).join('/'));
    }
  }
  return prefixes.size === 1 ? [...prefixes][0] : undefined;
}

/** Rewrite relative product mesh URLs to `<bucket>/<url>` (CreateSingle parity). */
export function rewriteMeshUrls(meshes, bucket) {
  if (!bucket || !meshes) return 0;
  const prefix = String(bucket).replace(/\/$/, '');
  let rewritten = 0;
  for (const mesh of Object.values(meshes)) {
    if (!mesh || typeof mesh.url !== 'string' || !mesh.url) continue;
    if (ABSOLUTE_URL.test(mesh.url) || mesh.url.startsWith(`${prefix}/`)) continue;
    mesh.url = `${prefix}/${mesh.url.replace(/^\//, '')}`;
    rewritten++;
  }
  return rewritten;
}

/** Remap replaceId → newModelId inside a visibility / state map. */
export function remapIdMap(map, replaceId, newModelId) {
  if (!map || typeof map !== 'object') return map;
  if (!(replaceId in map)) return map;
  const next = { ...map };
  if (!(newModelId in next)) next[newModelId] = next[replaceId];
  delete next[replaceId];
  return next;
}

function remapViewRefs(views, replaceId, newModelId) {
  if (!views) return;
  for (const view of Object.values(views)) {
    if (!view || typeof view !== 'object') continue;
    if (view.model_group_visibility) {
      view.model_group_visibility = remapIdMap(view.model_group_visibility, replaceId, newModelId);
    }
  }
}

/** Apply duplicateModel idMapping to a product visibility map (ROOT → new root). */
function remapVisibilityWithMapping(map, idMapping, newModelId) {
  if (!map || typeof map !== 'object') return map;
  const next = {};
  for (const [id, visible] of Object.entries(map)) {
    if (id === ROOT_ENTITY_ID) next[newModelId] = visible;
    else next[idMapping[id] ?? id] = visible;
  }
  return next;
}

/**
 * 等价于可影 duplicateModel(json, modelId)：对 modelId 子树（沿 children 递归）
 * 生成新 uuid，旧 key 从 models 删除，新 key 追加；容器节点的 children 全部按映射改写；
 * 新根的 type 设为 'group'。就地修改 json，与可影一致。
 */
export function duplicateModel(json, modelId, newId = randomUUID) {
  const idMapping = {};
  const duplicate = (id) => {
    const model = json.models[id];
    if (!model) throw new Error(`duplicateModel: models 中不存在 ${id}`);
    const newModelId = newId();
    const newModel = structuredClone(model);
    json.models[newModelId] = newModel;
    delete json.models[id];
    idMapping[id] = newModelId;
    if (isContainer(model)) {
      for (const child of model.children) duplicate(child);
      json.models[newModelId].type = 'group';
    }
    return newModelId;
  };
  const newModelId = duplicate(modelId);
  for (const key of Object.keys(json.models)) {
    const group = json.models[key];
    if (isContainer(group)) {
      group.children = group.children.map((c) => (idMapping[c] ? idMapping[c] : c));
    }
  }
  return { modelData: json, newModelId, idMapping };
}

/**
 * 等价于可影 handleCreateScene 的纯数据部分。
 * @param {object} p
 * @param {object} p.sceneTemplateData 模板 Scene JSON
 * @param {object} p.singleSceneData   单品 Scene JSON
 * @param {string} p.replaceId         模板中占位 group 的 id（template.replace_id）
 * @param {() => string} [p.newId]     uuid 生成器（测试可注入，默认 crypto.randomUUID）
 * @param {string} [p.productBucket]   产品 data_bucket_url；缺省时尝试推断
 * @returns {{ scene: object, newModelId: string, replaceIdParent: string|undefined, idMapping: Record<string,string> }}
 */
export function mergeSceneTemplate({ sceneTemplateData, singleSceneData, replaceId, newId = randomUUID, productBucket }) {
  if (!replaceId) throw new Error('缺少 replaceId（可影对此直接 onCreateError）');
  if (!sceneTemplateData?.models) throw new Error('sceneTemplateData.models 缺失');
  if (!singleSceneData?.models?.[ROOT_ENTITY_ID]) throw new Error('singleSceneData.models[ROOT] 缺失');

  // 不污染调用方数据（可影的数据是刚 fetch 的临时对象，这里等价于一份拷贝）
  const tpl = structuredClone(sceneTemplateData);
  const single = structuredClone(singleSceneData);
  // duplicateModel 会改写 models；相机 / 视图 / mesh URL 改写仍以产品原稿为准
  const productCameras = structuredClone(single.cameras ?? {});
  const productViews = structuredClone(single.views ?? {});
  const bucket = inferProductBucket(single, productBucket);
  rewriteMeshUrls(single.meshes, bucket);

  const replacedGroup = tpl.models[replaceId];
  if (!replacedGroup) throw new Error(`模板 models 中不存在 replaceId=${replaceId}`);

  // 1) 占位 group 浅合并到单品 ROOT：占位属性（name/position/rotation_euler/scale/type 等）覆盖，children 保留单品自己的
  single.models[ROOT_ENTITY_ID] = {
    ...single.models[ROOT_ENTITY_ID],
    ...replacedGroup,
    children: single.models[ROOT_ENTITY_ID].children,
  };

  // 2) duplicateModel：整棵单品子树换新 uuid，根改为 group
  const { modelData, newModelId, idMapping } = duplicateModel(single, ROOT_ENTITY_ID, newId);
  modelData.models[newModelId].type = 'group';

  // 3) 递归删除模板中 replaceId 及其后代
  const deleteEntity = (entityId) => {
    const entity = tpl.models[entityId];
    if (entity) {
      delete tpl.models[entityId];
      if (isContainer(entity)) entity.children.forEach(deleteEntity);
    }
  };
  deleteEntity(replaceId);

  // 4) 父节点 children：去掉 replaceId，末尾追加 newModelId
  const replaceIdParent = Object.keys(tpl.models).find((key) => tpl.models[key]?.children?.includes(replaceId));
  if (replaceIdParent) {
    tpl.models[replaceIdParent].children = [
      ...tpl.models[replaceIdParent].children.filter((child) => child !== replaceId),
      newModelId,
    ];
  } else {
    // 可影此处静默不挂载，产物里会丢产品；薄层改为显式失败
    throw new Error(`模板中找不到 children 含 replaceId=${replaceId} 的父节点`);
  }

  // 5) 按 key 合并；decals 的 ROOT.children 为两侧拼接；灯光 / 环境 / scene_settings 仍取自模板
  const tplDecalRoot = tpl.decals?.[ROOT_ENTITY_ID];
  const prodDecalRoot = modelData.decals?.[ROOT_ENTITY_ID];
  const scene = {
    ...tpl,
    models: { ...tpl.models, ...modelData.models },
    materials: { ...tpl.materials, ...modelData.materials },
    textures: { ...tpl.textures, ...modelData.textures },
    decals: {
      ...tpl.decals,
      ...modelData.decals,
      [ROOT_ENTITY_ID]: {
        ...tplDecalRoot,
        children: [...(tplDecalRoot?.children ?? []), ...(prodDecalRoot?.children ?? [])],
      },
    },
    meshes: { ...tpl.meshes, ...modelData.meshes },
    // F2：保留产品相机，供切正视图 / 特写；模板相机仍在
    cameras: { ...tpl.cameras, ...productCameras },
  };

  // F2：views 的 model_group_visibility 把 replaceId remap 到新根
  remapViewRefs(scene.views, replaceId, newModelId);

  // F2：并入产品视图（id 不冲突时），可见性表按 duplicate 映射改写
  for (const [viewId, view] of Object.entries(productViews)) {
    if (!view || scene.views?.[viewId]) continue;
    const next = structuredClone(view);
    if (next.model_group_visibility) {
      next.model_group_visibility = remapVisibilityWithMapping(next.model_group_visibility, idMapping, newModelId);
    }
    scene.views = scene.views ?? {};
    scene.views[viewId] = next;
  }

  return { scene, newModelId, replaceIdParent, idMapping };
}
function parseArgs(argv) {
  const opts = {};
  const keys = {
    '--template': 'template',
    '--product': 'product',
    '--replace-id': 'replaceId',
    '--out': 'out',
    '--product-bucket': 'productBucket',
  };
  for (let i = 0; i < argv.length; i++) {
    const k = keys[argv[i]];
    if (argv[i] === '-h' || argv[i] === '--help') opts.help = true;
    else if (!k || argv[i + 1] === undefined) throw new Error(`无法识别的参数: ${argv[i]}`);
    else opts[k] = argv[++i];
  }
  return opts;
}

function main() {
  const usage =
    'node merge_scene_template.mjs --template <tpl.json> --product <product.json> --replace-id <uuid> --out <out.json> [--product-bucket <url>]';
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(`${e.message}\n用法: ${usage}`);
    process.exit(2);
  }
  if (opts.help || !opts.template || !opts.product || !opts.replaceId || !opts.out) {
    console.error(`用法: ${usage}`);
    process.exit(opts.help ? 0 : 2);
  }
  try {
    const sceneTemplateData = JSON.parse(readFileSync(opts.template, 'utf8'));
    const singleSceneData = JSON.parse(readFileSync(opts.product, 'utf8'));
    const { scene, newModelId, replaceIdParent } = mergeSceneTemplate({
      sceneTemplateData,
      singleSceneData,
      replaceId: opts.replaceId,
      productBucket: opts.productBucket,
    });
    mkdirSync(dirname(resolve(opts.out)), { recursive: true });
    writeFileSync(opts.out, JSON.stringify(scene));
    console.error(
      `merged: newModelId=${newModelId} parent=${replaceIdParent} models=${Object.keys(scene.models).length} cameras=${Object.keys(scene.cameras ?? {}).length} views=${Object.keys(scene.views ?? {}).length} -> ${opts.out}`,
    );
  } catch (e) {
    console.error(`merge 失败: ${e.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) main();
