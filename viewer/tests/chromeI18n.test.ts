import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const root = path.resolve(__dirname, '..');
const read = (rel: string) => readFileSync(path.join(root, rel), 'utf8');

const CHROME = [
  'src/components/Inspector.tsx',
  'src/components/SceneTree.tsx',
  'src/components/Toolbar.tsx',
  'src/components/Viewport.tsx',
  'src/components/StatusBar.tsx',
  'src/components/ViewModeBar.tsx',
  'src/components/ViewControls.tsx',
  'src/components/panels/MaterialPanel.tsx',
  'src/components/ExamplesBrowser.tsx',
  'src/components/SceneTemplatePanel.tsx',
];

const REQUIRED = [
  '实时查看', '高质量预览', '提交渲染',
  '场景模板', '灯光', '材质', '相机', '渲染', '场景',
  '打开', '导出', '示例',
  '搜索对象', '未选择材质', '适配模型',
];

const FORBIDDEN = [
  'Search objects',
  'No material selected',
  'Drop to open',
  'Fit to model',
  'Hide inspector',
  'Show inspector',
  'Open files…',
  '>Examples<',
  "label: 'Lighting'",
  "label: 'Material'",
  "label: 'Camera'",
  "label: 'Render'",
  '<h2>Scene</h2>',
];

describe('viewer chrome i18n', () => {
  const bundle = CHROME.map(read).join('\n');

  it('keeps F2 mode labels and key Chinese chrome copy', () => {
    for (const phrase of REQUIRED) {
      expect(bundle, phrase).toContain(phrase);
    }
  });

  it('drops key English chrome leftovers (proper nouns are allow-listed elsewhere)', () => {
    for (const phrase of FORBIDDEN) {
      expect(bundle, phrase).not.toContain(phrase);
    }
  });

  it('does not rename Living Room presets into 场景模板', () => {
    const presets = read('src/engine/presets.ts');
    // Living Room (if present) stays a model preset name, not a scene-template label.
    expect(read('src/components/SceneTemplatePanel.tsx')).not.toContain('Living Room');
    if (presets.includes('Living Room')) {
      expect(presets).toContain('Living Room');
    }
  });
});
