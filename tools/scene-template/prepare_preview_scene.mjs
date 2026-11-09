#!/usr/bin/env node
// 从合并后的 scene 派生"本机可渲染"的预览 scene（m2-merged.json 本身不改）。
// mutracer-render 对资源缺失直接报错，而模板 GLB / 贴图（official_asset 桶）不在本地备份里，
// 所以这里把 asset map 里没有的 mesh 节点设为 is_visible=false，并清掉指向缺失贴图的材质引用。
// 另外：合并结果的相机/视图取自模板，模板相机朝向与单品朝向不一定对得上（冰箱正面朝 -y，
// 模板 cam_01 在 +y 侧朝 -y 看会拍到背面），所以可选地把单品自己的某个视图相机注入到预览 scene 的
// 目标视图里（仅预览派生物，不进 m2-merged.json）。
// 用法: node prepare_preview_scene.mjs <merged.json> <asset-map.json> <out-scene.json> [<product.json> <product-view-id> <merged-view-id>]
import { readFileSync, writeFileSync } from 'node:fs';

const [mergedPath, mapPath, outPath, productPath, productView, mergedView] = process.argv.slice(2);
if (!outPath) {
  console.error('用法: prepare_preview_scene.mjs <merged.json> <asset-map.json> <out-scene.json>');
  process.exit(2);
}
const scene = JSON.parse(readFileSync(mergedPath, 'utf8'));
const assets = JSON.parse(readFileSync(mapPath, 'utf8'));

let hiddenModels = 0;
const missingMeshes = new Set();
for (const m of Object.values(scene.models)) {
  if (m.type !== 'model' || !m.mesh || m.is_visible === false) continue;
  const url = scene.meshes[m.mesh]?.url;
  if (!url || !(url in assets)) {
    m.is_visible = false;
    hiddenModels++;
    if (url) missingMeshes.add(url);
  }
}

const badTextures = new Set(
  Object.entries(scene.textures ?? {})
    .filter(([, t]) => !t || !((t.urls ?? t.url) in assets))
    .map(([id]) => id),
);
let clearedRefs = 0;
for (const mat of Object.values(scene.materials ?? {})) {
  for (const [k, v] of Object.entries(mat)) {
    if (typeof v === 'string' && badTextures.has(v)) {
      mat[k] = '';
      clearedRefs++;
    }
  }
}
if (productPath) {
  const product = JSON.parse(readFileSync(productPath, 'utf8'));
  const camId = product.views?.[productView]?.active_camera;
  const cam = product.cameras?.[camId];
  const view = scene.views?.[mergedView];
  if (!cam || !view) throw new Error(`找不到单品视图相机 ${productView} 或合并视图 ${mergedView}`);
  scene.cameras[camId] = cam;
  view.active_camera = camId;
  console.error(`preview camera: product view ${productView} (${camId}) -> merged view ${mergedView}`);
}
writeFileSync(outPath, JSON.stringify(scene));
console.error(
  `preview scene: hidden ${hiddenModels} models (${missingMeshes.size} missing glb), cleared ${clearedRefs} texture refs -> ${outPath}`,
);
