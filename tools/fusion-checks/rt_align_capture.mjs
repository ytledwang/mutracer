#!/usr/bin/env node
/**
 * Capture the realtime (and optionally quality) canvas at the Front view with a
 * 16:9 output aspect, headed Chrome + ANGLE Metal, against the running viewer on
 * 127.0.0.1:3012 (never starts/stops it). Usage:
 *   node rt_align_capture.mjs --out DIR --tag NAME [--view ID]
 * Writes DIR/realtime-<tag>.png and DIR/capture-<tag>.json; exit 1 on error.
 */
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire('/tmp/mutracer-f2/package.json')('playwright');
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const OUT = opt('--out'); const TAG = opt('--tag', 'rt');
const VIEW = opt('--view', '1c4a3883-8668-4c16-a10e-0b7c24272279');
const SWEEP = opt('--sweep') ? JSON.parse(opt('--sweep')) : null; // [{tag, lights:{fill,ground,key}, exposure}]
mkdirSync(OUT, { recursive: true });
const errors = [];
const browser = await chromium.launch({ channel: 'chrome', headless: false,
  args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-webgpu', '--disable-features=CalculateNativeWinOcclusion'] });
let code = 0;
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on('pageerror', (e) => errors.push(`PAGEERROR ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`CONSOLE ${m.text()}`); });
  await page.goto('http://127.0.0.1:3012/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!(window.__MUTRACER_F2__?.ready?.()), { timeout: 60000 });
  await page.waitForTimeout(1500);
  const applied = await page.evaluate(() => window.__MUTRACER_F2__.applyM2());
  if (!applied?.ok) throw new Error('applyM2 failed ' + JSON.stringify(applied));
  await page.waitForTimeout(2500);
  await page.evaluate(() => window.__MUTRACER_F2__.setOutputAspect(16 / 9));
  await page.evaluate((id) => window.__MUTRACER_F2__.applyView(id), VIEW);
  await page.evaluate(() => window.__MUTRACER_F2__.setViewMode('realtime'));
  await page.waitForTimeout(2500);
  await page.addStyleTag({ content: '.float,.viewport-bottom,.selection-box,.focus-frame,.debug-overlay,[class*="toast"]{visibility:hidden!important}' });
  await page.waitForTimeout(300);
  if (SWEEP) {
    for (const s of SWEEP) {
      await page.evaluate((l) => window.__MUTRACER_F2__.setRealtimeLights(l), s.lights || {});
      await page.waitForTimeout(600);
      await page.locator('canvas[data-view-mode="realtime"]').screenshot({ path: path.join(OUT, `realtime-${s.tag}.png`), type: 'png' });
    }
  }
  const file = path.join(OUT, `realtime-${TAG}.png`);
  await page.locator('canvas[data-view-mode="realtime"]').screenshot({ path: file, type: 'png' });
  const snap = await page.evaluate(() => window.__MUTRACER_F2__.snapshot());
  const box = await page.locator('canvas[data-view-mode="realtime"]').boundingBox();
  writeFileSync(path.join(OUT, `capture-${TAG}.json`), JSON.stringify({ file, box, camera: snap.camera, viewId: snap.viewId, viewMode: snap.viewMode, applied, errors }, null, 2));
  console.log(JSON.stringify({ file, box, viewId: snap.viewId, errors: errors.length }));
  if (snap.viewMode !== 'realtime' || snap.viewId !== VIEW) code = 1;
} catch (e) {
  console.error('ERROR', e.message); code = 1;
} finally {
  await browser.close();
}
process.exit(code);
