import { describe, expect, it, vi } from 'vitest';

vi.hoisted(() => vi.stubGlobal('location', { search: '', hash: '' }));

import { DEFAULT_SETTINGS, useViewer } from '../src/store';
import {
  M2_REPLACE_ID,
  OFFICIAL_KITCHEN_REPLACE_ID,
  templateAcceptance,
  templateBadge,
} from '../src/engine/sceneTemplateCatalog';
import {
  hideMissingMeshModels,
  listSceneViews,
  resolveAssetHref,
  type StageScene,
} from '../src/engine/sceneJson';

function localRemap(map: Record<string, boolean>, replaceId: string, newModelId: string) {
  if (!(replaceId in map)) return map;
  const next = { ...map };
  if (!(newModelId in next)) next[newModelId] = next[replaceId];
  delete next[replaceId];
  return next;
}

describe('F2 viewMode vs previewEnabled', () => {
  it('defaults to realtime and keeps previewEnabled independent', () => {
    const state = useViewer.getState();
    expect(state.viewMode).toBe('realtime');
    expect(state.settings.previewEnabled).toBe(DEFAULT_SETTINGS.previewEnabled);
    expect(Object.keys(state.settings)).toContain('previewEnabled');
    expect(Object.keys(state.settings)).not.toContain('viewMode');
  });
});

describe('scene template catalog acceptance', () => {
  it('marks official kitchen ccdaa114 as 不可验收 without rewriting the id', () => {
    const official = {
      id: 5,
      type: 'scene_template',
      name: '冰箱厨房场景',
      replace_id: OFFICIAL_KITCHEN_REPLACE_ID,
      data_bucket_url: 'official_asset/template/RF_Kitchen_0302_Scene',
    };
    expect(templateAcceptance(official)).toBe('unavailable');
    expect(templateBadge(templateAcceptance(official))).toBe('不可验收');
    expect(official.replace_id).toBe('ccdaa114-cdb7-4ef5-af26-022938a780d5');
    expect(official.replace_id).not.toBe(M2_REPLACE_ID);
  });

  it('keeps M2 replace_id as a separate fixture id', () => {
    expect(M2_REPLACE_ID).toBe('c83a2f4a-0a3d-4494-8da9-37e6ca6943a7');
    expect(templateAcceptance({ replace_id: M2_REPLACE_ID })).toBe('ok');
  });

  it('marks missing replace_id as 不可用', () => {
    expect(templateAcceptance({ replace_id: null })).toBe('unusable');
    expect(templateBadge('unusable')).toBe('不可用');
  });
});

describe('scene.json + asset map adapter helpers', () => {
  it('hides models whose mesh url is absent from the asset map', () => {
    const scene: StageScene = {
      models: {
        a: { type: 'model', mesh: 'm1', is_visible: true },
        b: { type: 'model', mesh: 'm2', is_visible: true },
      },
      meshes: {
        m1: { url: 'customer_asset/prod/a.glb' },
        m2: { url: 'official_asset/template/kitchen/wall.glb' },
      },
    };
    const hidden = hideMissingMeshModels(scene, { 'customer_asset/prod/a.glb': '/tmp/a.glb' });
    expect(hidden).toBe(1);
    expect(scene.models!.a.is_visible).not.toBe(false);
    expect(scene.models!.b.is_visible).toBe(false);
  });

  it('resolves asset hrefs through the F2 middleware key', () => {
    const href = resolveAssetHref(
      { 'customer_asset/prod/a.glb': '/Users/x/a.glb' },
      'customer_asset/prod/a.glb',
    );
    expect(href).toBe(`/api/f2/asset?key=${encodeURIComponent('customer_asset/prod/a.glb')}`);
  });

  it('lists views for the camera switcher', () => {
    const views = listSceneViews({
      views: {
        '1c4a3883-8668-4c16-a10e-0b7c24272279': { name: 'Front', active_camera: 'cam' },
      },
    });
    expect(views).toEqual([
      { id: '1c4a3883-8668-4c16-a10e-0b7c24272279', name: 'Front', cameraId: 'cam' },
    ]);
  });

  it('remaps replaceId visibility for F2 view switching', () => {
    const map = { [M2_REPLACE_ID]: true, other: false };
    const next = localRemap(map, M2_REPLACE_ID, 'new-root');
    expect(next).toEqual({ other: false, 'new-root': true });
    expect(M2_REPLACE_ID in next).toBe(false);
  });
});
