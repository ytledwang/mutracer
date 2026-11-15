/**
 * Read-only stage scene.json + asset map types and helpers for F2 (plan A).
 * Viewer adapts these into the existing Three scene; it does not re-merge templates.
 */

export const ROOT_ENTITY_ID = '00000000-0000-0000-0000-000000000000';

export type ViewMode = 'realtime' | 'qualityPreview';

export interface StageVec3 {
  0: number;
  1: number;
  2: number;
}

export interface StageModelNode {
  type?: string;
  name?: string;
  children?: string[];
  mesh?: string;
  is_visible?: boolean;
  position?: number[];
  rotation_euler?: number[];
  scale?: number[];
}

export interface StageMesh {
  type?: string;
  name?: string;
  materials?: string[];
  url?: string;
}

export interface StageMaterial {
  type?: string;
  name?: string;
  base_color_rgb?: number[];
  metallic?: number;
  roughness?: number;
  transmission?: number;
  ior?: number;
  [key: string]: unknown;
}

export interface StageCamera {
  type?: string;
  name?: string;
  children?: string[];
  position?: number[];
  rotation_euler?: number[];
  fov?: number;
  look_at?: number[];
  [key: string]: unknown;
}

export interface StageView {
  name?: string;
  active_camera?: string;
  active_environment?: string;
  model_group_visibility?: Record<string, boolean>;
  [key: string]: unknown;
}

export interface StageScene {
  models?: Record<string, StageModelNode>;
  meshes?: Record<string, StageMesh>;
  materials?: Record<string, StageMaterial>;
  textures?: Record<string, unknown>;
  cameras?: Record<string, StageCamera>;
  views?: Record<string, StageView>;
  lights?: Record<string, unknown>;
  environments?: Record<string, unknown>;
  scene_settings?: Record<string, unknown>;
  decals?: Record<string, unknown>;
}

/** url key → absolute filesystem path or http(s) / vite URL */
export type AssetMap = Record<string, string>;

export interface SceneDocument {
  scene: StageScene;
  assetMap: AssetMap;
  /** Display name in the viewer chrome. */
  name: string;
  /** Preferred view id after load (merged Front, etc.). */
  preferredViewId?: string | null;
}

export interface SceneViewInfo {
  id: string;
  name: string;
  cameraId: string | null;
}

export function listSceneViews(scene: StageScene): SceneViewInfo[] {
  return Object.entries(scene.views ?? {}).map(([id, view]) => ({
    id,
    name: view.name || id.slice(0, 8),
    cameraId: view.active_camera ?? null,
  }));
}

export function resolveAssetHref(assetMap: AssetMap, url: string | undefined): string | null {
  if (!url) return null;
  const mapped = assetMap[url];
  if (!mapped) return null;
  if (/^(https?:|blob:|data:)/i.test(mapped)) return mapped;
  if (mapped.startsWith('/')) {
    // Absolute FS path → F2 Vite middleware, or already a site path.
    if (mapped.startsWith('/api/') || mapped.startsWith('/@fs/')) return mapped;
    return `/api/f2/asset?key=${encodeURIComponent(url)}`;
  }
  // Relative map value: still go through the key so the server resolves it.
  return `/api/f2/asset?key=${encodeURIComponent(url)}`;
}

/** Hide model nodes whose mesh URL is absent from the asset map (kitchen shell gap). */
export function hideMissingMeshModels(scene: StageScene, assetMap: AssetMap): number {
  let hidden = 0;
  for (const node of Object.values(scene.models ?? {})) {
    if (node.type !== 'model' || !node.mesh || node.is_visible === false) continue;
    const url = scene.meshes?.[node.mesh]?.url;
    if (!url || !(url in assetMap)) {
      node.is_visible = false;
      hidden++;
    }
  }
  return hidden;
}

export function applyEulerYXZ(object: { rotation: { set: (x: number, y: number, z: number) => void } }, eulerDeg?: number[]) {
  if (!eulerDeg || eulerDeg.length < 3) return;
  const toRad = Math.PI / 180;
  object.rotation.set(eulerDeg[0] * toRad, eulerDeg[1] * toRad, eulerDeg[2] * toRad);
}

export function applyTransform(
  object: { position: { set: (x: number, y: number, z: number) => void }; scale: { set: (x: number, y: number, z: number) => void }; rotation: { set: (x: number, y: number, z: number) => void } },
  node: StageModelNode | StageCamera,
) {
  const p = node.position;
  if (p && p.length >= 3) object.position.set(p[0], p[1], p[2]);
  const s = (node as StageModelNode).scale;
  if (s && s.length >= 3) object.scale.set(s[0], s[1], s[2]);
  applyEulerYXZ(object, node.rotation_euler);
}
