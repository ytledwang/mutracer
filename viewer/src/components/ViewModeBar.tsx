import { showToast, useViewer } from '../store';
import { getEngine } from '../engine/ViewerEngine';
import { submitFinalRender } from '../engine/submitFinalRender';
import { Segmented } from './ui/controls';

/**
 * F2 三分法文案：实时查看 / 高质量预览 / 提交渲染。
 * 不复用 previewEnabled（Interactive preview）。
 */
export function ViewModeBar() {
  const viewMode = useViewer((s) => s.viewMode);
  const templateApplied = useViewer((s) => s.fusionTemplateApplied);
  const fusionScene = useViewer((s) => s.fusionScene);
  const model = useViewer((s) => s.model);
  const busy = useViewer((s) => s.loading !== null);

  // 套模板后必须先落在实时查看；套完（templateApplied）才开高质量。普通 GLB 无 fusion 载荷时可直接切。
  const qualityBlocked = busy || !model || (fusionScene !== null && !templateApplied);
  const submitBlocked = busy || !fusionScene?.viewId || !templateApplied;

  return (
    <div className="view-mode-bar float" role="group" aria-label="查看与渲染模式">
      <Segmented
        label="查看模式"
        value={viewMode}
        disabled={busy}
        onChange={(mode) => {
          if (mode === 'qualityPreview' && qualityBlocked) {
            showToast('请先套模板并在实时查看中确认结果', 'warning');
            return;
          }
          getEngine()?.setViewMode(mode);
        }}
        options={[
          { value: 'realtime', label: '实时查看' },
          { value: 'qualityPreview', label: '高质量预览', disabled: qualityBlocked },
        ]}
      />
      <button
        type="button"
        className="btn"
        disabled={submitBlocked}
        title={fusionScene ? '提交到本机 Blender 成片（非 8787 预览）' : '需要已合并的 scene.json'}
        aria-label="提交渲染"
        onClick={() => {
          void (async () => {
            if (!fusionScene) return;
            try {
              showToast('正在提交本机成片…', 'info');
              const result = await submitFinalRender({
                payload: fusionScene,
                dryRun: false,
                width: 640,
                height: 360,
                spp: 4,
              });
              showToast(result.message, result.ok ? 'success' : 'error');
            } catch (error) {
              try {
                const dry = await submitFinalRender({ payload: fusionScene, dryRun: true });
                showToast(`成片调用失败，已改为 dry-run：${dry.message}（${(error as Error).message}）`, 'warning');
              } catch (dryError) {
                showToast(`提交渲染失败：${(dryError as Error).message}`, 'error');
              }
            }
          })();
        }}
      >
        提交渲染
      </button>
    </div>
  );
}
