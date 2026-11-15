/**
 * Plan A adapter: load a read-only stage scene.json + asset map into a Three Object3D tree.
 * Does not merge templates and does not export a whole-scene GLB.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import * as meshopt from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import type { LoadedModel, LoadProgress } from './loadModel';
import { finalLookMaterial } from './finalLook';
import {
  ROOT_ENTITY_ID,
  hideMissingMeshModels,
  listSceneViews,
  resolveAssetHref,
  type AssetMap,
  type SceneDocument,
  type SceneViewInfo,
  type StageCamera,
  type StageMaterial,
  type StageModelNode,
  type StageScene,
} from './sceneJson';
import {
  applyThreeWorld,
  cameraWorldThree,
  groupWorldThree,
  meshWorldThree,
  ueLocalMatrix,
} from './ueBasis';

export interface LoadedSceneDocument extends LoadedModel {
  sceneDocument: SceneDocument;
  sceneViews: SceneViewInfo[];
  /** Model-group id → Object3D (for view visibility). */
  groupNodes: Map<string, THREE.Object3D>;
  /** Camera id → PerspectiveCamera created from scene.cameras. */
  stageCameras: Map<string, THREE.PerspectiveCamera>;
  hiddenMissing: number;
}

let sharedDraco: DRACOLoader | undefined;

function gltfLoader() {
  const loader = new GLTFLoader();
  sharedDraco ??= new DRACOLoader();
  loader.setDRACOLoader(sharedDraco);
  loader.setMeshoptDecoder((meshopt as unknown as { MeshoptDecoder: Parameters<GLTFLoader['setMeshoptDecoder']>[0] }).MeshoptDecoder);
  return loader;
}

function loadGltf(url: string, signal?: AbortSignal): Promise<THREE.Group> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
      return;
    }
    const loader = gltfLoader();
    const onAbort = () => {
      loader.manager.itemError(url);
      reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
    loader.load(
      url,
      (gltf) => {
        signal?.removeEventListener('abort', onAbort);
        resolve(gltf.scene);
      },
      undefined,
      (err) => {
        signal?.removeEventListener('abort', onAbort);
        reject(err);
      },
    );
  });
}

async function mapPool<T, R>(items: T[], limit: number, worker: (item: T, index: number) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const i = next++;
      results[i] = await worker(items[i], i);
    }
  });
  await Promise.all(runners);
  return results;
}

function toColor(rgb?: number[]) {
  if (!rgb || rgb.length < 3) return new THREE.Color(0.8, 0.8, 0.8);
  return new THREE.Color(rgb[0], rgb[1], rgb[2]);
}

function applyStageMaterial(mesh: THREE.Mesh, mat: StageMaterial | undefined) {
  if (!mat) return;
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  for (const material of materials) {
    if (!(material instanceof THREE.MeshStandardMaterial) && !(material instanceof THREE.MeshPhysicalMaterial)) continue;
    if (mat.name) material.name = mat.name;
    if (mat.base_color_rgb) material.color.copy(toColor(mat.base_color_rgb));
    if (typeof mat.metallic === 'number') material.metalness = mat.metallic;
    if (typeof mat.roughness === 'number') material.roughness = mat.roughness;
    if (material instanceof THREE.MeshPhysicalMaterial) {
      if (typeof mat.transmission === 'number') material.transmission = mat.transmission;
      if (typeof mat.ior === 'number') material.ior = mat.ior;
    }
    material.needsUpdate = true;
  }
}

/**
 * Resolve each instance's material the way 提交渲染 does (blender_inner.py material_override),
 * using the view camera's space for the left/right and upper/lower rules.
 */
function applyFinalLook(
  scene: StageScene,
  viewId: string | null,
  stageCameras: Map<string, THREE.PerspectiveCamera>,
  root: THREE.Object3D,
  targets: { holder: THREE.Object3D; material: StageMaterial; meshName: string }[],
) {
  if (!targets.length) return;
  const views = scene.views ?? {};
  const view = (viewId && views[viewId]) || Object.values(views)[0];
  const camera = (view?.active_camera && stageCameras.get(view.active_camera)) || stageCameras.values().next().value;
  root.updateMatrixWorld(true);
  const inverse = camera ? camera.matrixWorld.clone().invert() : new THREE.Matrix4();
  const box = new THREE.Box3();
  const corner = new THREE.Vector3();
  for (const { holder, material, meshName } of targets) {
    box.makeEmpty();
    holder.traverse((obj) => {
      const m = obj as THREE.Mesh;
      if (!m.isMesh || !m.geometry) return;
      if (!m.geometry.boundingBox) m.geometry.computeBoundingBox();
      const bb = m.geometry.boundingBox!;
      for (let i = 0; i < 8; i++) {
        corner.set(i & 1 ? bb.max.x : bb.min.x, i & 2 ? bb.max.y : bb.min.y, i & 4 ? bb.max.z : bb.min.z);
        box.expandByPoint(corner.applyMatrix4(m.matrixWorld).applyMatrix4(inverse));
      }
    });
    if (box.isEmpty()) continue;
    const side = (box.min.x + box.max.x) / 2;
    const height = (box.min.y + box.max.y) / 2;
    const look = finalLookMaterial(material, meshName, side, height);
    holder.traverse((obj) => {
      const m = obj as THREE.Mesh;
      if (!m.isMesh) return;
      const list = (Array.isArray(m.material) ? m.material : [m.material]).map((src) => {
        if (!(src instanceof THREE.MeshStandardMaterial)) return src;
        const mat = src.clone();
        mat.color.setRGB(look.color[0], look.color[1], look.color[2]);
        mat.roughness = look.roughness;
        mat.metalness = look.metalness;
        if (look.emit > 0) { mat.emissive.setRGB(look.color[0], look.color[1], look.color[2]); mat.emissiveIntensity = look.emit; }
        if (mat instanceof THREE.MeshPhysicalMaterial) {
          if (look.glass) { mat.transmission = 0.9; mat.ior = 1.45; }
          if (look.lacquer) { mat.clearcoat = 0.8; mat.clearcoatRoughness = 0.1; }
        }
        mat.userData.finalLook = true;
        mat.needsUpdate = true;
        return mat;
      });
      m.material = Array.isArray(m.material) ? list : list[0];
    });
  }
}

function cameraFov(cam: StageCamera): number {
  const nested = (cam as StageCamera & { camera?: { fov?: number } }).camera?.fov;
  return nested ?? cam.fov ?? 35;
}

function createStageCamera(id: string, cam: StageCamera): THREE.PerspectiveCamera | null {
  if (cam.type === 'root') return null;
  if (cam.type === 'group') return null;
  if (cam.children && cam.children.length && cam.type !== 'camera' && cam.type !== 'free') return null;
  const camera = new THREE.PerspectiveCamera(cameraFov(cam), 1, 0.01, 1000);
  camera.name = cam.name || `Camera ${id.slice(0, 8)}`;
  camera.userData.stageCameraId = id;
  // UE / blender_inner.py treat stage fov as horizontal (sensor_fit HORIZONTAL);
  // ViewerEngine.setAspect converts it to Three's vertical fov per aspect.
  camera.userData.horizontalFov = cameraFov(cam);
  // Placement is applied later in UE→Three space (same stack as blender_inner.py).
  const ue = ueLocalMatrix(cam, false);
  applyThreeWorld(camera, cameraWorldThree(ue));
  return camera;
}

function composeUeWorlds(scene: StageScene): Map<string, THREE.Matrix4> {
  const worlds = new Map<string, THREE.Matrix4>();
  const walk = (id: string, parent: THREE.Matrix4) => {
    const node = scene.models?.[id];
    if (!node) return;
    const world = parent.clone().multiply(ueLocalMatrix(node, true));
    worlds.set(id, world);
    for (const childId of node.children ?? []) walk(childId, world);
  };
  for (const [id, node] of Object.entries(scene.models ?? {})) {
    if (node.type === 'root') walk(id, new THREE.Matrix4());
  }
  return worlds;
}

function applyStageWorlds(
  scene: StageScene,
  groupNodes: Map<string, THREE.Object3D>,
  worlds: Map<string, THREE.Matrix4>,
) {
  const apply = (id: string) => {
    const node = scene.models?.[id];
    const object = groupNodes.get(id);
    const ue = worlds.get(id);
    if (object && ue) {
      const meshHolder = node?.type === 'model' && !!node.mesh;
      applyThreeWorld(object, meshHolder ? meshWorldThree(ue) : groupWorldThree(ue));
    }
    for (const childId of node?.children ?? []) apply(childId);
  };
  for (const [id, node] of Object.entries(scene.models ?? {})) {
    if (node.type === 'root') apply(id);
  }
}

/**
 * Build a LoadedModel from a stage scene document. Missing asset-map meshes are hidden
 * (official kitchen shell gap) instead of failing the load.
 */
export async function loadSceneDocument(
  document: SceneDocument,
  onProgress: LoadProgress,
  signal?: AbortSignal,
): Promise<LoadedSceneDocument> {
  const scene: StageScene = structuredClone(document.scene);
  const assetMap: AssetMap = { ...document.assetMap };
  const hiddenMissing = hideMissingMeshModels(scene, assetMap);

  const root = new THREE.Group();
  root.name = document.name || 'scene.json';
  root.userData.mutracerSceneDocument = true;

  const groupNodes = new Map<string, THREE.Object3D>();
  const stageCameras = new Map<string, THREE.PerspectiveCamera>();
  const meshCache = new Map<string, THREE.Object3D>();

  // Unique visible mesh URLs
  const jobs: { modelId: string; node: StageModelNode; href: string; meshId: string }[] = [];
  for (const [modelId, node] of Object.entries(scene.models ?? {})) {
    if (node.type !== 'model' || !node.mesh || node.is_visible === false) continue;
    const mesh = scene.meshes?.[node.mesh];
    const href = resolveAssetHref(assetMap, mesh?.url);
    if (!href) continue;
    jobs.push({ modelId, node, href, meshId: node.mesh });
  }

  let loaded = 0;
  onProgress('download', 0, jobs.length);
  const uniqueHrefs = [...new Set(jobs.map((j) => j.href))];
  await mapPool(uniqueHrefs, 8, async (href) => {
    signal?.throwIfAborted();
    try {
      const gltfRoot = await loadGltf(href, signal);
      meshCache.set(href, gltfRoot);
    } catch (error) {
      console.warn('[scene.json] mesh load failed', href, error);
      meshCache.set(href, new THREE.Group());
    }
    loaded++;
    onProgress('download', loaded, uniqueHrefs.length);
  });
  signal?.throwIfAborted();
  onProgress('parse');

  const lookTargets: { holder: THREE.Object3D; material: StageMaterial; meshName: string }[] = [];
  const buildNode = (id: string): THREE.Object3D | null => {
    if (groupNodes.has(id)) return groupNodes.get(id)!;
    const node = scene.models?.[id];
    if (!node) return null;

    if (node.type === 'model' && node.mesh) {
      const mesh = scene.meshes?.[node.mesh];
      const href = resolveAssetHref(assetMap, mesh?.url);
      const holder = new THREE.Group();
      holder.name = node.name || mesh?.name || id.slice(0, 8);
      holder.userData.stageModelId = id;
      holder.visible = node.is_visible !== false;
      if (href && meshCache.has(href)) {
        const clone = meshCache.get(href)!.clone(true);
        const matId = mesh?.materials?.[0];
        const stageMat = matId ? scene.materials?.[matId] : undefined;
        clone.traverse((obj) => {
          const m = obj as THREE.Mesh;
          if (m.isMesh) applyStageMaterial(m, stageMat);
        });
        holder.add(clone);
        if (stageMat) lookTargets.push({ holder, material: stageMat, meshName: String(mesh?.name ?? '') });
      }
      groupNodes.set(id, holder);
      return holder;
    }

    const group = new THREE.Group();
    group.name = node.name || (id === ROOT_ENTITY_ID ? root.name : id.slice(0, 8));
    group.userData.stageModelId = id;
    group.visible = node.is_visible !== false;
    groupNodes.set(id, group);
    for (const childId of node.children ?? []) {
      const child = buildNode(childId);
      if (child) group.add(child);
    }
    return group;
  };

  const sceneRoot = buildNode(ROOT_ENTITY_ID) ?? root;
  if (sceneRoot !== root) {
    root.add(sceneRoot);
    // Keep ROOT mapping for view visibility keyed on product root after merge.
    groupNodes.set(ROOT_ENTITY_ID, sceneRoot);
  }

  const ueWorlds = composeUeWorlds(scene);
  applyStageWorlds(scene, groupNodes, ueWorlds);

  for (const [camId, cam] of Object.entries(scene.cameras ?? {})) {
    const camera = createStageCamera(camId, cam);
    if (!camera) continue;
    stageCameras.set(camId, camera);
    root.add(camera);
  }

  applyFinalLook(scene, document.preferredViewId ?? null, stageCameras, root, lookTargets);

  return {
    name: document.name,
    root,
    animations: [],
    sceneDocument: { ...document, scene },
    sceneViews: listSceneViews(scene),
    groupNodes,
    stageCameras,
    hiddenMissing,
    revoke() {
      // GLTFLoader blob URLs are not used; asset middleware serves files.
    },
  };
}

/** Apply a named stage view: camera + model_group_visibility on already-loaded nodes. */
export function applySceneView(
  loaded: LoadedSceneDocument,
  viewId: string,
): { camera: THREE.PerspectiveCamera | null; cameraIndexHint: number } {
  const view = loaded.sceneDocument.scene.views?.[viewId];
  if (!view) return { camera: null, cameraIndexHint: -1 };

  const visibility = view.model_group_visibility;
  if (visibility) {
    for (const [id, visible] of Object.entries(visibility)) {
      const node = loaded.groupNodes.get(id);
      if (node) node.visible = visible;
    }
  }

  const camId = view.active_camera;
  const camera = camId ? loaded.stageCameras.get(camId) ?? null : null;
  if (!camera) return { camera: null, cameraIndexHint: -1 };

  // cameraIndex is resolved by ViewerEngine against modelCameras order.
  return { camera, cameraIndexHint: -1 };
}

export function findCameraIndex(modelCameras: THREE.Object3D[], stageCamera: THREE.Object3D | null): number {
  if (!stageCamera) return -1;
  return modelCameras.findIndex((c) => c === stageCamera || c.userData.stageCameraId === stageCamera.userData.stageCameraId);
}
