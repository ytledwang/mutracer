import { useState } from 'react';
import { Layers } from 'lucide-react';
import samples from '../engine/scene-templates.sample.json';
import { Field, Hint, Section } from './ui/controls';

interface SceneTemplate {
  id: number;
  type: string;
  name: string;
  replace_id: string | null;
  data_bucket_url: string;
}

const templates = (samples as SceneTemplate[]).filter((t) => t.type === 'scene_template');

export function SceneTemplatePanel() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = templates.find((t) => t.id === selectedId) ?? null;
  return (
    <>
      <Section title="场景模板" icon={<Layers size={14} />} value={templates.length}>
        <div className="tpl-list" role="listbox" aria-label="场景模板">
          {templates.map((t) => {
            const usable = !!t.replace_id;
            return (
              <button
                key={t.id}
                role="option"
                aria-selected={t.id === selectedId}
                className="tpl-row"
                data-selected={t.id === selectedId || undefined}
                data-unusable={!usable || undefined}
                onClick={() => setSelectedId(t.id)}
              >
                <span className="label">{t.name}</span>
                <span className="meta">{t.type}</span>
                <span className="tpl-badge" data-ok={usable || undefined}>{usable ? 'replace_id' : '不可用'}</span>
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
            {!selected.replace_id && <Hint warn>缺少 replace_id，无法合并。</Hint>}
          </>
        ) : (
          <Hint>选择一个模板查看详情。</Hint>
        )}
        <Hint>
          合并预览：<span className="tpl-value">tools/scene-template/run_m2_demo.sh</span>
          {selected?.replace_id && <> （REPLACE_ID={selected.replace_id}）</>}
          ，输出 tools/scene-template/out/m2-preview.png。
        </Hint>
      </Section>
    </>
  );
}
