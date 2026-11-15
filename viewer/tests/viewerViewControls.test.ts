import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => vi.stubGlobal('location', { search: '', hash: '' }));
vi.mock('../src/engine/ViewerEngine', () => ({ getEngine: () => null }));

import { CameraControls } from '../src/components/ViewControls';
import { DEFAULT_SETTINGS, useViewer } from '../src/store';

const initialState = { ...useViewer.getInitialState() };
afterEach(() => Object.assign(useViewer.getInitialState(), initialState));

describe('viewport camera controls', () => {
  it.each([[], ['Front'], ['Front', 'Side']])('keeps fit available with cameras %j', (...cameras) => {
    Object.assign(useViewer.getInitialState(), {
      settings: { ...DEFAULT_SETTINGS, cameraIndex: -1 },
      cameras
    });
    const markup = renderToStaticMarkup(createElement(CameraControls));
    expect(markup).toContain('aria-label="适配模型"');
    expect(markup).toContain('title="适配模型 (F)"');
    expect(markup.includes('aria-label="相机"')).toBe(cameras.length > 0);
  });
});
