#!/usr/bin/env node
/**
 * F2 live acceptance (headed Chrome on the Mac mini GPU when available).
 * Writes new evidence under --evidence (default: docs/prd/evidence/fusion/f2/r2).
 * Does not overwrite last night's r1 screenshots. Exits 1 if any item fails;
 * every item is still recorded.
 */
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, openSync, readFileSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function loadPlaywright() {
  const roots = [
    process.env.PLAYWRIGHT_REQUIRE_ROOT,
    '/tmp/mutracer-f2/package.json',
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'package.json'),
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../package.json'),
  ].filter(Boolean);
  let last;
  for (const root of roots) {
    try {
      return createRequire(root)('playwright');
    } catch (error) {
      last = error;
    }
  }
  throw last ?? new Error('playwright not found; set PLAYWRIGHT_REQUIRE_ROOT to a package.json that can require it');
}
const { chromium } = loadPlaywright();

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const args = process.argv.slice(2);
const evIdx = args.indexOf('--evidence');
const EV = evIdx >= 0 ? args[evIdx + 1] : path.join(ROOT, 'docs/prd/evidence/fusion/f2/r2');
mkdirSync(EV, { recursive: true });

const PORT = 3012;
const BASE = `http://127.0.0.1:${PORT}/`;
const GOOD = path.join(ROOT, 'tools/import-contract/fixtures/good-named-pivot.glb');
const FRONT_VIEW = '1c4a3883-8668-4c16-a10e-0b7c24272279';
const CLOSE_VIEW = 'da307f8c-a522-4ec9-a1fe-03f7092e1dfc'; // 新相机2 close-ish
const M2_ID = 'c83a2f4a-0a3d-4494-8da9-37e6ca6943a7';
const IMAGE_STATS = path.join(ROOT, 'tools/fusion-checks/f2_image_stats.py');

const items = [];
const notes = [];
const consoleErrors = [];
let headedOnRealGpu = false;
let launchMode = 'unknown';
let weStartedViewer = false;
let viewerProc = null;

function note(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  notes.push(line);
}

function record(name, status, extra = {}) {
  items.push({ name, status, ...extra });
  note(`${status}  ${name}${extra.exit != null ? ` exit=${extra.exit}` : ''}${extra.detail ? ` — ${extra.detail}` : ''}`);
}

function sha256File(file) {
  return createHash('sha256').update(readFileSync(file)).digest('hex');
}

function imageStats(file, expectVisible = true) {
  const jsonOut = file + '.stats.json';
  const cmd = ['python3', IMAGE_STATS, file, '--json-out', jsonOut];
  if (expectVisible) cmd.push('--expect-visible');
  const r = spawnSync(cmd[0], cmd.slice(1), { encoding: 'utf8' });
  let stats = null;
  if (existsSync(jsonOut)) {
    try { stats = JSON.parse(readFileSync(jsonOut, 'utf8'))[0]; } catch {}
  }
  return { exit: r.status ?? 1, stats, stderr: r.stderr };
}

function httpOk(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => { res.resume(); resolve(res.statusCode && res.statusCode < 500); });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

async function ensureViewer() {
  if (await httpOk(BASE)) {
    note(`reusing viewer at ${BASE}`);
    return;
  }
  const logPath = path.join(EV, 'viewer.log');
  const outFd = openSync(logPath, 'a');
  viewerProc = spawn('npx', ['vite', '--config', 'viewer/vite.config.ts', '--host', '127.0.0.1', '--port', String(PORT)], {
    cwd: ROOT,
    stdio: ['ignore', outFd, outFd],
    env: { ...process.env, BROWSER: 'none' },
  });
  weStartedViewer = true;
  writeFileSync(path.join(EV, 'viewer.pid'), String(viewerProc.pid));
  const start = Date.now();
  while (Date.now() - start < 60_000) {
    if (await httpOk(BASE)) {
      note(`started viewer pid=${viewerProc.pid}`);
      return;
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`viewer did not start on ${BASE}; see ${logPath}`);
}

async function launchBrowser() {
  const attempts = [
    {
      mode: 'headed-chrome-metal',
      realGpu: true,
      options: {
        channel: 'chrome',
        headless: false,
        args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-webgpu', '--disable-features=CalculateNativeWinOcclusion'],
      },
    },
    {
      mode: 'headed-chromium',
      realGpu: true,
      options: {
        headless: false,
        args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-webgpu'],
      },
    },
  ];
  let lastErr;
  for (const attempt of attempts) {
    try {
      const browser = await chromium.launch({
        ...attempt.options,
        viewport: null,
      });
      launchMode = attempt.mode;
      headedOnRealGpu = attempt.realGpu;
      note(`launched ${attempt.mode}`);
      return browser;
    } catch (error) {
      lastErr = error;
      note(`launch ${attempt.mode} failed: ${error.message}`);
    }
  }
  throw lastErr ?? new Error('could not launch a headed browser');
}

async function waitProbe(page, timeout = 30_000) {
  await page.waitForFunction(() => !!(window.__MUTRACER_F2__ && window.__MUTRACER_F2__.ready && window.__MUTRACER_F2__.ready()), { timeout });
}

async function snap(page) {
  return page.evaluate(() => window.__MUTRACER_F2__.snapshot());
}

async function screenshotCanvas(page, mode, file) {
  const loc = page.locator(`canvas[data-view-mode="${mode}"]`);
  await loc.screenshot({ path: file, type: 'png' });
  return file;
}

function camerasClose(a, b, posTol = 0.02, fovTol = 0.15) {
  if (!a || !b) return { ok: false, reason: 'missing camera snapshot' };
  const dpos = Math.hypot(
    (a.position?.[0] ?? 0) - (b.position?.[0] ?? 0),
    (a.position?.[1] ?? 0) - (b.position?.[1] ?? 0),
    (a.position?.[2] ?? 0) - (b.position?.[2] ?? 0),
  );
  const dtarget = Math.hypot(
    (a.target?.[0] ?? 0) - (b.target?.[0] ?? 0),
    (a.target?.[1] ?? 0) - (b.target?.[1] ?? 0),
    (a.target?.[2] ?? 0) - (b.target?.[2] ?? 0),
  );
  const dfov = Math.abs((a.fov ?? 0) - (b.fov ?? 0));
  const ok = dpos <= posTol && dtarget <= posTol && dfov <= fovTol;
  return { ok, dpos, dtarget, dfov };
}

function materialsEqual(a, b) {
  const key = (list) => (list || []).map((m) => `${m.mesh}::${m.material}`).sort();
  const ka = key(a), kb = key(b);
  return { ok: JSON.stringify(ka) === JSON.stringify(kb), countA: ka.length, countB: kb.length };
}

async function switchMode(page, mode) {
  await page.evaluate((m) => window.__MUTRACER_F2__.setViewMode(m), mode);
  await page.waitForTimeout(300);
}

async function waitSpp(page, minSpp = 1, timeout = 45_000) {
  const start = Date.now();
  let last = 0;
  while (Date.now() - start < timeout) {
    const s = await snap(page);
    last = s?.spp ?? 0;
    if (last >= minSpp && (s?.phase === 'converging' || s?.phase === 'denoising' || s?.phase === 'finished' || s?.phase === 'previewing')) {
      return s;
    }
    if (s?.phase === 'error') return s;
    await page.waitForTimeout(500);
  }
  return await snap(page);
}

function aovErrors() {
  return consoleErrors.filter((t) => /AOV_REFLECTANCE/i.test(t));
}

async function run() {
  await ensureViewer();
  const browser = await launchBrowser();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.setDefaultTimeout(60_000);
  page.on('pageerror', (e) => { consoleErrors.push(`PAGEERROR: ${e.message}`); note(`PAGEERROR: ${e.message}`); });
  page.on('console', (msg) => {
    if (['error', 'warning'].includes(msg.type())) {
      const t = `CONSOLE ${msg.type()}: ${msg.text()}`;
      consoleErrors.push(t);
      if (msg.type() === 'error' || /AOV_REFLECTANCE|Shader Error/i.test(t)) note(t);
    }
  });

  try {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await waitProbe(page);
    const info = await page.evaluate(() => window.__MUTRACER_F2__.backend?.() ?? null);
    note(`backend=${JSON.stringify(info)} launch=${launchMode}`);

    // ---- labels chrome (for hash distinctness) ----
    const labelsFile = path.join(EV, 'f2-mode-labels-r2.png');
    await page.locator('.view-mode-bar').screenshot({ path: labelsFile });
    record('mode-labels screenshot', 'PASS', { path: labelsFile, sha256: sha256File(labelsFile) });

    // ---- F1 good fixture realtime + pick by name ----
    consoleErrors.length = 0;
    await page.locator('#open-files').setInputFiles(GOOD);
    await page.waitForFunction(() => {
      const s = window.__MUTRACER_F2__?.snapshot?.();
      return s && s.meshCount > 0 && !s.loading;
    }, { timeout: 60_000 });
    await page.waitForTimeout(1500);
    const f1RealFile = path.join(EV, 'f1-named-materials-realtime-r2.png');
    const f1RealCanvas = path.join(EV, 'f1-named-materials-realtime-canvas-r2.png');
    await page.screenshot({ path: f1RealFile });
    await screenshotCanvas(page, 'realtime', f1RealCanvas);
    const f1RealStats = imageStats(f1RealCanvas, true);
    record('F1 good fixture realtime visible', f1RealStats.exit === 0 ? 'PASS' : 'FAIL', {
      exit: f1RealStats.exit, path: f1RealCanvas, fullPage: f1RealFile, stats: f1RealStats.stats, sha256: sha256File(f1RealCanvas),
    });

    const picked = await page.evaluate(() => window.__MUTRACER_F2__.pickMaterialByName('Fridge_White'));
    await page.waitForTimeout(800);
    const f1PickFile = path.join(EV, 'f1-named-materials-picked-r2.png');
    await page.screenshot({ path: f1PickFile });
    record('F1 pick material by name Fridge_White', picked?.ok ? 'PASS' : 'FAIL', {
      path: f1PickFile, detail: JSON.stringify(picked), sha256: sha256File(f1PickFile),
    });

    // ---- Apply M2 and realtime ----
    const applied = await page.evaluate(async () => window.__MUTRACER_F2__.applyM2());
    if (!applied?.ok) {
      record('apply M2 fixture', 'FAIL', { detail: JSON.stringify(applied) });
    } else {
      record('apply M2 fixture', 'PASS', { detail: `replaceId=${applied.replaceId || M2_ID}` });
    }
    if (applied?.replaceId && applied.replaceId !== M2_ID) {
      record('M2 replace_id is c83a2f4a-… only', 'FAIL', { detail: applied.replaceId });
    } else if (applied?.ok) {
      record('M2 replace_id is c83a2f4a-… only', 'PASS', { detail: M2_ID });
    }
    await page.waitForTimeout(2000);
    await page.evaluate((id) => window.__MUTRACER_F2__.applyView(id), FRONT_VIEW);
    await page.waitForTimeout(800);

    const rtFile = path.join(EV, 'f2-realtime-after-template-r2.png');
    const rtCanvas = path.join(EV, 'f2-realtime-after-template-canvas-r2.png');
    await page.screenshot({ path: rtFile });
    await screenshotCanvas(page, 'realtime', rtCanvas);
    const rtStats = imageStats(rtCanvas, true);
    record('M2 realtime canvas shows fridge (not black)', rtStats.exit === 0 ? 'PASS' : 'FAIL', {
      exit: rtStats.exit, path: rtCanvas, fullPage: rtFile, stats: rtStats.stats, sha256: sha256File(rtCanvas),
    });

    const beforeQuality = await snap(page);
    if (beforeQuality && beforeQuality.inView === false) {
      record('M2 Front view has visible meshes in camera frustum', 'FAIL', { detail: JSON.stringify(beforeQuality.bounds || beforeQuality.camera) });
    } else {
      record('M2 Front view has visible meshes in camera frustum', 'PASS', { detail: JSON.stringify(beforeQuality?.bounds || null) });
    }

    // ---- Quality preview, same state (do not orbit first — that used to move the camera) ----
    const aovBefore = aovErrors().length;
    await switchMode(page, 'qualityPreview');
    const qualitySnap = await waitSpp(page, 1, 45_000);
    const aovNew = aovErrors().slice(aovBefore);
    const qFile = path.join(EV, 'f2-quality-after-template-r2.png');
    const qCanvas = path.join(EV, 'f2-quality-after-template-canvas-r2.png');
    await page.screenshot({ path: qFile });
    await screenshotCanvas(page, 'qualityPreview', qCanvas);
    const qStats = imageStats(qCanvas, true);
    const qHash = sha256File(qCanvas);
    const rtHash = sha256File(rtCanvas);
    const labelHash = sha256File(labelsFile);
    const hashesDiffer = qHash !== rtHash && qHash !== labelHash && rtHash !== labelHash;
    record('quality preview no AOV_REFLECTANCE error', aovNew.length === 0 ? 'PASS' : 'FAIL', {
      detail: aovNew.join(' | ') || 'none',
    });
    record('quality preview spp advances > 0', (qualitySnap?.spp ?? 0) > 0 && qualitySnap?.phase !== 'error' ? 'PASS' : 'FAIL', {
      detail: `spp=${qualitySnap?.spp} phase=${qualitySnap?.phase}`,
    });
    record('quality canvas shows fridge', qStats.exit === 0 ? 'PASS' : 'FAIL', {
      exit: qStats.exit, path: qCanvas, fullPage: qFile, stats: qStats.stats, sha256: qHash,
    });
    record('quality sha256 differs from realtime and labels', hashesDiffer ? 'PASS' : 'FAIL', {
      detail: JSON.stringify({ quality: qHash, realtime: rtHash, labels: labelHash }),
    });

    const afterQuality = await snap(page);
    const cam = camerasClose(beforeQuality?.camera, afterQuality?.camera);
    const mats = materialsEqual(beforeQuality?.materials, afterQuality?.materials);
    record('switch to quality keeps camera (pos/target/fov)', cam.ok ? 'PASS' : 'FAIL', { detail: JSON.stringify(cam) });
    record('switch to quality keeps material assignments', mats.ok ? 'PASS' : 'FAIL', { detail: JSON.stringify(mats) });

    // ---- Orbit timing in realtime, then restore the Front view ----
    await switchMode(page, 'realtime');
    const orbit = await page.evaluate(async () => window.__MUTRACER_F2__.orbitTiming(2500));
    const orbitPath = path.join(EV, 'f2-orbit-timing-r2.json');
    writeFileSync(orbitPath, JSON.stringify(orbit, null, 2));
    const fpsOk = (orbit?.fps?.avg ?? 0) > 5 && (orbit?.frames ?? 0) >= 10;
    record('realtime orbit timing log', fpsOk ? 'PASS' : 'FAIL', { path: orbitPath, detail: JSON.stringify(orbit?.fps || orbit) });
    await page.evaluate((id) => window.__MUTRACER_F2__.applyView(id), FRONT_VIEW);
    await page.waitForTimeout(400);

    // ---- Front + close-up: realtime then quality ----
    for (const [label, viewId] of [['front', FRONT_VIEW], ['closeup', CLOSE_VIEW]]) {
      await switchMode(page, 'realtime');
      await page.evaluate((id) => window.__MUTRACER_F2__.applyView(id), viewId);
      await page.waitForTimeout(800);
      const rFull = path.join(EV, `f2-${label}-realtime-r2.png`);
      const rCan = path.join(EV, `f2-${label}-realtime-canvas-r2.png`);
      await page.screenshot({ path: rFull });
      await screenshotCanvas(page, 'realtime', rCan);
      const rSt = imageStats(rCan, true);
      record(`${label} realtime visible`, rSt.exit === 0 ? 'PASS' : 'FAIL', {
        exit: rSt.exit, path: rCan, fullPage: rFull, stats: rSt.stats, sha256: sha256File(rCan),
      });
      const before = await snap(page);
      const aovN = aovErrors().length;
      await switchMode(page, 'qualityPreview');
      const qs = await waitSpp(page, 1, 45_000);
      const qFull = path.join(EV, `f2-${label}-quality-r2.png`);
      const qCan = path.join(EV, `f2-${label}-quality-canvas-r2.png`);
      await page.screenshot({ path: qFull });
      await screenshotCanvas(page, 'qualityPreview', qCan);
      const qSt = imageStats(qCan, true);
      const after = await snap(page);
      const c = camerasClose(before?.camera, after?.camera);
      const m = materialsEqual(before?.materials, after?.materials);
      const aov = aovErrors().slice(aovN);
      record(`${label} quality visible, spp>0, no AOV, camera+materials consistent`,
        (qSt.exit === 0 && (qs?.spp ?? 0) > 0 && aov.length === 0 && c.ok && m.ok) ? 'PASS' : 'FAIL',
        {
          exit: qSt.exit,
          path: qCan,
          fullPage: qFull,
          sha256: sha256File(qCan),
          spp: qs?.spp,
          phase: qs?.phase,
          aov: aov,
          camera: c,
          materials: m,
          stats: qSt.stats,
        });
    }

    // Official id not rewritten: probe catalog
    const catalog = await page.evaluate(() => window.__MUTRACER_F2__.catalog?.() ?? null);
    const officialOk = catalog?.official?.replaceId === 'ccdaa114-cdb7-4ef5-af26-022938a780d5'
      && catalog?.official?.badge === '不可验收'
      && catalog?.official?.replaceId !== M2_ID;
    record('official kitchen ccdaa114 stays 不可验收 (not rewritten to M2)', officialOk ? 'PASS' : 'FAIL', {
      detail: JSON.stringify(catalog?.official || catalog),
    });
  } catch (error) {
    record('f2_check.mjs uncaught', 'FAIL', { detail: error.stack || error.message });
  } finally {
    const report = {
      launchMode,
      headedOnRealGpu,
      items,
      notes,
      consoleErrors: consoleErrors.slice(-80),
    };
    writeFileSync(path.join(EV, 'f2-ui-report.json'), JSON.stringify(report, null, 2));
    writeFileSync(path.join(EV, 'f2-check.mjs.log'), notes.join('\n') + '\n');
    await browser.close().catch(() => {});
    if (weStartedViewer && viewerProc && !viewerProc.killed) {
      // leave the viewer running for demo / later rounds; just note the pid
      note(`viewer left running pid=${viewerProc.pid}`);
    }
  }

  const failed = items.filter((i) => i.status !== 'PASS').length;
  note(`UI check done: ${items.length - failed} passed, ${failed} failed, launch=${launchMode}, realGpu=${headedOnRealGpu}`);
  process.exit(failed ? 1 : 0);
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
