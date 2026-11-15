import { useState } from 'react';
import { Layers } from 'lucide-react';
import samples from '../engine/scene-templates.sample.json';
import { Field, Hint, Section } from './ui/controls';
import { getEngine } from '../engine/ViewerEngine';
import { showToast, useViewer } from '../store';
import type { SceneDocument } from '../engine/sceneJson';
import {
  M2_REPLACE_ID,
  OFFICIAL_KITCHEN_REPLACE_ID,
  templateAcceptance,
  templateBadge,
  type CatalogTemplate,
} from '../engine/sceneTemplateCatalog';

const templates = (samples as CatalogTemplate[]).filter((t) => t.type === 'scene_template');

export function SceneTemplatePanel() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [applying, setApplying] = useState(false);
  const fusionApplied = useViewer((s) => s.fusionTemplateApplied);
  const selected = templates.find((t) => t.id === selectedId) ?? null;
  const selectedAcceptance = selected ? templateAcceptance(selected) : null;

  return (
    <>
      <Section title="场景模板" icon={<Layers size={14} />} value={templates.length}>
        <div className="tpl-list" role="listbox" aria-label="场景模板">
          {templates.map((t) => {
            const state = templateAcceptance(t);
            const badge = templateBadge(state);
            return (
              <button
                key={t.id}
                role="option"
                aria-selected={t.id === selectedId}
                className="tpl-row"
                data-selected={t.id === selectedId || undefined}
                data-unusable={state !== 'ok' || undefined}
                data-unavailable={state === 'unavailable' || undefined}
                onClick={() => setSelectedId(t.id)}
              >
                <span className="label">{t.name}</span>
                <span className="meta">{t.type}</span>
                <span className="tpl-badge" data-ok={state === 'ok' || undefined} data-blocked={state !== 'ok' || undefined}>
                  {badge}
                </span>
              </button>
            );
          })}
        </div>
      </Section>
      <Section title="详情">
        {selected ? (
          <>
            <Field label="id"><span className="tpl-value">{selected.id}</span></Field>
            <Field label="replace_id"><span className="tpl-value">{selected.replace_id ?? '—'}</span></Field>
            <Field label="data_bucket_url"><span className="tpl-value">{selected.data_bucket_url}</span></Field>
            {selectedAcceptance === 'unusable' && <Hint warn>缺少 replace_id，无法合并。</Hint>}
            {selectedAcceptance === 'unavailable' && (
              <Hint warn>
                官方壳 RF_Kitchen_0302_Scene（{OFFICIAL_KITCHEN_REPLACE_ID}）不在本机，本项不可验收。
                不要改成 M2 的 {M2_REPLACE_ID}。合并预览里厨房 mesh 会被隐藏；本轮只验状态同步与模式切换。
              </Hint>
            )}
          </>
        ) : (
          <Hint>选择一个模板查看详情。</Hint>
        )}
        <Hint>
          开发夹具（本机 M2）：replace_id=<span className="tpl-value">{M2_REPLACE_ID}</span>
          ，模板 fixtures/real/template-fridge-kitchen.json + 冰箱单品。
        </Hint>
        <button
          type="button"
          className="btn btn--wide"
          disabled={applying}
          aria-label="套用本机 M2 模板"
          onClick={() => {
            void (async () => {
              setApplying(true);
              try {
                const res = await fetch('/api/f2/apply-m2', { method: 'POST' });
                const body = await res.json() as SceneDocument & {
                  error?: string;
                  preferredViewId?: string;
                  note?: string;
                };
                if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
                const doc: SceneDocument = {
                  name: body.name,
                  scene: body.scene,
                  assetMap: body.assetMap,
                  preferredViewId: body.preferredViewId ?? null,
                };
                const ok = await getEngine()?.loadSceneJsonDocument(doc, { templateApplied: true });
                if (ok === false) showToast('加载合并结果失败', 'error');
                else if (body.note) console.info('[f2]', body.note);
              } catch (error) {
                showToast(`套用 M2 失败：${(error as Error).message}`, 'error');
              } finally {
                setApplying(false);
              }
            })();
          }}
        >
          {applying ? '合并并加载中…' : fusionApplied ? '重新套用本机 M2 夹具' : '套用本机 M2 夹具（实时查看）'}
        </button>
      </Section>
    </>
  );
}
