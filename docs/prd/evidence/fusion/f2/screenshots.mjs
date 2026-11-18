import { chromium } from 'playwright';
import path from 'node:path';
import { mkdirSync, writeFileSync } from 'node:fs';

const ROOT = '/Users/wangjianzheng/Project/git/mutracer';
const EV = path.join(ROOT, 'docs/prd/evidence/fusion/f2');
mkdirSync(EV, { recursive: true });

const GOOD = path.join(ROOT, 'tools/import-contract/fixtures/good-named-pivot.glb');
const BAD = path.join(ROOT, 'tools/import-contract/fixtures/bad-flattened-palette.glb');

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(60_000);
const log = [];
const note = (m) => { console.log(m); log.push(m); };

page.on('pageerror', (e) => note(`PAGEERROR: ${e.message}`));
page.on('console', (msg) => {
  if (['error', 'warning'].includes(msg.type())) note(`CONSOLE ${msg.type()}: ${msg.text()}`);
});

try {
  await page.goto('http://127.0.0.1:3012/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  note('loaded viewer');

  // Dump mode-bar presence
  const bar = await page.locator('.view-mode-bar').count();
  const labels = await page.locator('.view-mode-bar').innerText().catch(() => 'MISSING');
  note(`view-mode-bar count=${bar} text=${JSON.stringify(labels)}`);
  writeFileSync(path.join(EV, 'dom-mode-bar.html'), await page.content());

  await page.locator('#open-files').setInputFiles(GOOD);
  await page.waitForTimeout(5000);
  await page.screenshot({ path: path.join(EV, 'f1-named-materials-realtime.png') });
  note('f1-named-materials-realtime.png');

  // ToggleButtons from react-aria may expose as radio/button; click by text.
  const quality = page.locator('.view-mode-bar').getByText('高质量预览', { exact: true });
  await quality.click({ timeout: 15_000 });
  await page.waitForTimeout(6000);
  await page.screenshot({ path: path.join(EV, 'f1-named-materials-quality.png') });
  note('f1-named-materials-quality.png');

  await page.locator('.view-mode-bar').getByText('实时查看', { exact: true }).click();
  await page.waitForTimeout(800);
  await page.locator('#open-files').setInputFiles(BAD);
  await page.waitForTimeout(3500);
  await page.screenshot({ path: path.join(EV, 'f1-bad-contract-toast.png') });
  note('f1-bad-contract-toast.png');

  // Inspector rail: 场景模板 tab
  await page.locator('nav.rail').getByRole('tab', { name: '场景模板' }).click();
  await page.waitForTimeout(800);
  await page.getByRole('option', { name: /冰箱厨房场景/ }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(EV, 'f2-catalog-official-unavailable.png') });
  note('f2-catalog-official-unavailable.png');

  await page.getByRole('button', { name: /套用本机 M2/ }).click();
  note('clicked apply M2');
  try {
    await page.waitForFunction(() => document.body.innerText.includes('已套模板') || document.body.innerText.includes('官方厨房壳'), { timeout: 180_000 });
    note('apply toast seen');
  } catch {
    note('apply toast wait timed out');
  }
  await page.waitForTimeout(8000);
  await page.screenshot({ path: path.join(EV, 'f2-realtime-after-template.png') });
  note('f2-realtime-after-template.png');

  const q2 = page.locator('.view-mode-bar').getByText('高质量预览', { exact: true });
  if (await q2.isEnabled()) {
    await q2.click();
    await page.waitForTimeout(10000);
    await page.screenshot({ path: path.join(EV, 'f2-quality-after-template.png') });
    note('f2-quality-after-template.png');
  } else {
    note('quality disabled after template');
  }

  await page.screenshot({ path: path.join(EV, 'f2-mode-labels.png') });
  note('f2-mode-labels.png');
} catch (error) {
  note(`SCREENSHOT_ERROR: ${error.message}`);
  await page.screenshot({ path: path.join(EV, 'f2-screenshot-error.png'), fullPage: true }).catch(() => {});
} finally {
  writeFileSync(path.join(EV, 'screenshots.log'), log.join('\n') + '\n');
  await browser.close();
}
