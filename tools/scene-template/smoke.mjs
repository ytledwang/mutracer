#!/usr/bin/env node
// 离线烟雾：真实 CLI 跑 2 组 fixture，并断言可影合并不变量。
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const R = '00000000-0000-0000-0000-000000000000';
const here = dirname(fileURLToPath(import.meta.url));
const cli = join(here, 'merge_scene_template.mjs');
const load = (p) => JSON.parse(readFileSync(join(here, p), 'utf8'));

const cases = [
  { name: 'synthetic', tpl: 'fixtures/synthetic-template.json', prod: 'fixtures/synthetic-product.json', replaceId: 'aaaaaaaa-0000-4000-8000-000000000010', out: 'out/merged-synthetic.json' },
  // 真实 local-stack 备份：冰箱厨房场景（占位=BingXiang group） + 3.FBX 单品
  { name: 'real', tpl: 'fixtures/real/template-fridge-kitchen.json', prod: 'fixtures/real/product-3fbx-single.json', replaceId: 'c83a2f4a-0a3d-4494-8da9-37e6ca6943a7', out: 'out/merged-smoke.json' },
];

for (const c of cases) {
  execFileSync('node', [cli, '--template', join(here, c.tpl), '--product', join(here, c.prod), '--replace-id', c.replaceId, '--out', join(here, c.out)], { stdio: ['ignore', 'ignore', 'inherit'] });
  const tpl = load(c.tpl), prod = load(c.prod), out = load(c.out);
  const ph = tpl.models[c.replaceId];

  // 占位子树被删除（含后代）
  const walk = (id, acc = []) => { acc.push(id); const m = tpl.models[id]; if (m?.children) m.children.forEach((k) => walk(k, acc)); return [...new Set(acc)]; };
  for (const id of walk(c.replaceId)) assert.ok(!(id in out.models), `${c.name}: 占位子树节点未删除 ${id}`);
  // 父节点 children：不含 replaceId，末尾为新产品根
  const parent = Object.keys(tpl.models).find((k) => tpl.models[k].children?.includes(c.replaceId));
  const pc = out.models[parent].children;
  assert.ok(!pc.includes(c.replaceId));
  const newId = pc[pc.length - 1];
  const nr = out.models[newId];
  assert.equal(nr.type, 'group');
  // 变换继承自占位，children 来自单品
  for (const k of ['name', 'position', 'rotation_euler', 'scale']) assert.deepEqual(nr[k], ph[k], `${c.name}: ${k}`);
  assert.equal(nr.children.length, prod.models[R].children.length);
  // 产品原 id 均不再出现（新 uuid），数量守恒
  const prodIds = Object.keys(prod.models).filter((k) => k !== R);
  for (const id of prodIds) assert.ok(!(id in out.models), `${c.name}: 产品旧 id 残留 ${id}`);
  const expectedModels = Object.keys(tpl.models).length - walk(c.replaceId).length + Object.keys(prod.models).length;
  assert.equal(Object.keys(out.models).length, expectedModels, `${c.name}: models 数量`);
  // 全部 children 引用都可解析
  for (const [k, m] of Object.entries(out.models)) for (const ch of m.children ?? []) assert.ok(ch in out.models, `${c.name}: ${k} 悬空 child ${ch}`);
  // key 合并
  for (const f of ['materials', 'textures', 'meshes']) for (const k of [...Object.keys(tpl[f] ?? {}), ...Object.keys(prod[f] ?? {})]) assert.ok(k in out[f], `${c.name}: ${f}.${k} 丢失`);
  assert.deepEqual(out.decals[R].children, [...tpl.decals[R].children, ...prod.decals[R].children]);
  // 灯光 / 环境 / scene_settings 仍取自模板
  for (const f of ['lights', 'environments', 'scene_settings']) assert.deepEqual(out[f], tpl[f], `${c.name}: ${f} 应取自模板`);
  // F2：产品相机保留；模板视图 remap replaceId → newRoot；产品视图并入
  for (const camId of Object.keys(prod.cameras ?? {})) assert.ok(camId in out.cameras, `${c.name}: 产品相机 ${camId} 丢失`);
  for (const camId of Object.keys(tpl.cameras ?? {})) assert.ok(camId in out.cameras, `${c.name}: 模板相机 ${camId} 丢失`);
  for (const [vid, view] of Object.entries(tpl.views ?? {})) {
    assert.ok(vid in out.views, `${c.name}: 模板视图 ${vid} 丢失`);
    const vis = out.views[vid].model_group_visibility ?? {};
    assert.ok(!(c.replaceId in vis), `${c.name}: views 仍引用 replaceId`);
    if (c.replaceId in (view.model_group_visibility ?? {})) {
      assert.ok(newId in vis, `${c.name}: views 未 remap 到新根`);
      assert.equal(vis[newId], view.model_group_visibility[c.replaceId]);
    }
  }
  for (const vid of Object.keys(prod.views ?? {})) {
    if (vid in (tpl.views ?? {})) continue;
    assert.ok(vid in out.views, `${c.name}: 产品视图 ${vid} 未并入`);
  }
  console.error(`ok ${c.name}: models=${Object.keys(out.models).length} newRoot=${newId} -> ${c.out}`);
}
