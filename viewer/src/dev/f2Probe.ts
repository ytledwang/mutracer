/**
 * Dev-only F2 acceptance probe. Attaches window.__MUTRACER_F2__ so
 * tools/fusion-checks/f2_check.mjs can read camera / materials / spp
 * and drive view-mode / view / material-pick / orbit timing.
 */
import { getEngine, REALTIME_LIGHTS } from '../engine/ViewerEngine';
import { setSettings, setUi, useViewer, type ViewMode } from '../store';
import { M2_REPLACE_ID, OFFICIAL_KITCHEN_REPLACE_ID, templateBadge } from '../engine/sceneTemplateCatalog';

type F2Camera = {
  name: string;
  index: number;
  position: number[];
  target: number[];
  fov: number | null;
  aspect: number | null;
};

export type F2Snapshot = {
  viewMode: ViewMode;
  viewId: string | null;
  templateApplied: boolean;
  loading: unknown;
  camera: F2Camera | null;
  materials: { mesh: string; material: string }[];
  selectedMaterial: string | null;
  spp: number;
  phase: string;
  meshCount: number;
  visibleMeshCount: number;
  backend: unknown;
};

function snapshot(): F2Snapshot {
  const engine = getEngine();
  const state = useViewer.getState();
  const probed = engine?.f2Snapshot?.() ?? null;
  return {
    viewMode: state.viewMode,
    viewId: state.fusionViewId,
    templateApplied: state.fusionTemplateApplied,
    loading: state.loading,
    camera: probed?.camera ?? null,
    materials: probed?.materials ?? [],
    selectedMaterial: state.material?.name ?? state.selection.materialId ?? null,
    spp: state.stats.samples,
    phase: state.stats.phase,
    meshCount: probed?.meshCount ?? 0,
    visibleMeshCount: probed?.visibleMeshCount ?? 0,
    backend: state.backend,
  };
}

const api = {
  ready: () => !!getEngine(),
  snapshot,
  backend: () => useViewer.getState().backend,
  setViewMode: (mode: ViewMode) => {
    getEngine()?.setViewMode(mode);
  },
  applyView: (viewId: string) => {
    getEngine()?.applyFusionView(viewId);
  },
  pickMaterialByName: (name: string) => {
    const engine = getEngine();
    const hit = engine?.f2FindMaterial?.(name) ?? null;
    if (!hit) return { ok: false, name };
    engine!.selectMaterial(hit.materialId, hit.objectId);
    setUi({ right: true, tab: 'material' });
    return { ok: true, name, ...hit };
  },
  orbitTiming: async (durationMs = 2500) => {
    const engine = getEngine();
    if (!engine?.f2OrbitTiming) return { ok: false, error: 'no f2OrbitTiming' };
    return engine.f2OrbitTiming(durationMs);
  },
  applyM2: async () => {
    const res = await fetch('/api/f2/apply-m2', { method: 'POST' });
    const body = await res.json();
    if (!res.ok) return { ok: false, error: body?.error || res.statusText, body };
    const ok = await getEngine()?.loadSceneJsonDocument(body, { templateApplied: true });
    return {
      ok: !!ok,
      replaceId: body.replaceId ?? M2_REPLACE_ID,
      preferredViewId: body.preferredViewId ?? null,
      note: body.note ?? null,
    };
  },
  /** Lock the viewport to an output aspect (e.g. 16/9) so realtime matches the final frame. */
  setOutputAspect: (aspect: number | null) => {
    setSettings({ outputAspect: aspect }, { record: false });
    return useViewer.getState().settings.outputAspect;
  },
  /** Calibration hook for rt_align_capture.mjs (dev only). */
  setRealtimeLights: (patch: Partial<typeof REALTIME_LIGHTS>) => Object.assign(REALTIME_LIGHTS, patch),
  catalog: () => ({
    official: {
      replaceId: OFFICIAL_KITCHEN_REPLACE_ID,
      badge: templateBadge('unavailable'),
      name: '冰箱厨房场景',
    },
    m2: M2_REPLACE_ID,
  }),
};

declare global {
  interface Window {
    __MUTRACER_F2__?: typeof api;
  }
}

window.__MUTRACER_F2__ = api;
