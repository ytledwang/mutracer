/**
 * F2「提交渲染」: hand the same scene.json + asset map + view to the local
 * Blender final track (`tools/dual-track/blender/run_blender_final.py`).
 * 8787 stays preview-only; this never posts to the cloud worker.
 */
import type { FusionScenePayload } from '../store';

export interface SubmitFinalOptions {
  payload: FusionScenePayload;
  /** When true, only validate argv / write inputs; skip Blender (evidence dry-run). */
  dryRun?: boolean;
  width?: number;
  height?: number;
  spp?: number;
  outName?: string;
}

export interface SubmitFinalResult {
  ok: boolean;
  dryRun: boolean;
  command: string[];
  logPath?: string;
  outPath?: string;
  message: string;
}

export async function submitFinalRender(options: SubmitFinalOptions): Promise<SubmitFinalResult> {
  const { payload, dryRun = false, width = 640, height = 360, spp = 4, outName } = options;
  if (!payload.viewId) {
    throw new Error('提交渲染需要当前视图（viewId）');
  }
  const response = await fetch('/api/f2/submit-final', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scene: payload.scene,
      assetMap: payload.assetMap,
      viewId: payload.viewId,
      name: payload.name,
      dryRun,
      width,
      height,
      spp,
      outName: outName ?? `f2-final-${Date.now()}.png`,
    }),
  });
  const body = await response.json().catch(() => ({})) as SubmitFinalResult & { error?: string };
  if (!response.ok) {
    throw new Error(body.error || body.message || `submit-final HTTP ${response.status}`);
  }
  return body;
}
