#!/usr/bin/env node
// M4: 从 M2 预览 scene 派生 M4 scene（m2-preview-scene.json 本身不改）。
//  1. 导入：把一个 GLB 作为新 mesh+model 挂到 model_root，并写入 asset map（key = scene 内 mesh url）。
//  2. 薄调参：环境 hdri_brightness、相机 post_processing exposure（可选）。
//  3. 多机位：把产品 scene 里的 N 个 view（含相机）克隆成合并 scene 的 views（沿用产品 view id）。
// 用法: node apply_thin_params.mjs --scene in.json --product product.json --asset-map map.json \
//   --glb path.glb --glb-key m4/chess.glb --glb-pos 0.9,-1.2,0 --glb-scale 0.5 \
//   --views id1,id2 --base-view <merged view> --hdri-brightness 1.2 --exposure 1.0 \
//   --out-scene out.json --out-map out-map.json
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const a = {};
for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
for (const k of ['scene', 'product', 'asset-map', 'glb', 'glb-key', 'views', 'base-view', 'out-scene', 'out-map'])
  if (!a[k]) { console.error(`missing --${k}`); process.exit(2); }
const nums = (s, d) => (s ? s.split(',').map(Number) : d);

const scene = JSON.parse(readFileSync(a.scene, 'utf8'));
const product = JSON.parse(readFileSync(a.product, 'utf8'));
const map = JSON.parse(readFileSync(a['asset-map'], 'utf8'));

// 1. import GLB
const meshId = 'm4-mesh-import', modelId = 'm4-model-import';
scene.meshes[meshId] = { type: 'mesh', name: 'm4-import', materials: [], url: a['glb-key'] };
const s = Number(a['glb-scale'] ?? 1);
scene.models[modelId] = {
  type: 'model', name: 'm4-import', mesh: meshId, is_visible: true, is_locked: false,
  position: nums(a['glb-pos'], [0, 0, 0]), rotation_euler: nums(a['glb-rot'], [0, 0, 0]), scale: [s, s, s],
  light_channels: [0], receive_decal: true,
};
const root = Object.values(scene.models).find((m) => m.type === 'root');
root.children.push(modelId);
map[a['glb-key']] = resolve(a.glb);

// 2. thin params
const changes = [];
if (a['hdri-brightness']) {
  for (const env of Object.values(scene.environments)) {
    changes.push(`hdri_brightness ${env.settings.hdri_brightness} -> ${a['hdri-brightness']}`);
    env.settings.hdri_brightness = Number(a['hdri-brightness']);
  }
}

// 3. multi-view: clone base view per product view, swap in the product camera
const base = scene.views[a['base-view']];
if (!base) throw new Error(`base view ${a['base-view']} not found`);
for (const vid of a.views.split(',')) {
  const camId = product.views?.[vid]?.active_camera;
  const cam = product.cameras?.[camId];
  if (!cam) throw new Error(`product view ${vid} has no camera`);
  if (a.exposure) {
    changes.push(`camera ${camId.slice(0, 8)} exposure ${cam.camera.post_processing_settings.exposure} -> ${a.exposure}`);
    cam.camera.post_processing_settings.exposure = Number(a.exposure);
  }
  scene.cameras[camId] = cam;
  scene.views[vid] = { ...structuredClone(base), name: product.views[vid].name ?? vid, active_camera: camId };
}
for (const v of Object.values(scene.views)) v.model_group_visibility[modelId] = true;

writeFileSync(a['out-scene'], JSON.stringify(scene));
writeFileSync(a['out-map'], JSON.stringify(map));
console.error(`m4 scene: +import ${a['glb-key']} (${a.glb}); views=${Object.keys(scene.views).length}; thin: ${changes.join('; ') || 'none'}`);
