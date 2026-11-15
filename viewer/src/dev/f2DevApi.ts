/**
 * Vite-only F2 helpers: serve asset-map files, merge M2 fixtures, submit local Blender final.
 * Imported by viewer/vite.config.ts — not shipped in the library package.
 */
import { createReadStream, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import type { Plugin } from 'vite';
import type { IncomingMessage, ServerResponse } from 'node:http';

const REPLACE_ID_M2 = 'c83a2f4a-0a3d-4494-8da9-37e6ca6943a7';
const PRODUCT_VIEW = '298cfe60-923d-44fb-a0d1-f2206b9a48e1';
const MERGED_VIEW = '1c4a3883-8668-4c16-a10e-0b7c24272279';

function readJson(file: string) {
  return JSON.parse(readFileSync(file, 'utf8'));
}

function sendJson(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(body));
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (c: Buffer) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

export function f2DevApi(repoRoot: string): Plugin {
  const templatePath = path.join(repoRoot, 'tools/scene-template/fixtures/real/template-fridge-kitchen.json');
  const productPath = path.join(repoRoot, 'tools/cloud-service/poc-out/fridge/assets/customer_asset/1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a/scene.json');
  const assetMapPath = path.join(repoRoot, 'tools/cloud-service/poc-out/fridge/stage-fridge-assets.json');
  const mergeModule = path.join(repoRoot, 'tools/scene-template/merge_scene_template.mjs');
  const prepareModule = path.join(repoRoot, 'tools/scene-template/prepare_preview_scene.mjs');
  const blenderFinal = path.join(repoRoot, 'tools/dual-track/blender/run_blender_final.py');
  const evidenceDir = path.join(repoRoot, 'docs/prd/evidence/fusion/f2');

  return {
    name: 'mutracer-viewer-f2-dev-api',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? '/', 'http://127.0.0.1');
        const loopback = /^(::1|127\.0\.0\.1|::ffff:127\.0\.0\.1)$/.test(req.socket.remoteAddress ?? '');

        if (url.pathname === '/api/f2/asset' && req.method === 'GET') {
          try {
            const key = url.searchParams.get('key');
            if (!key) return sendJson(res, 400, { error: 'missing key' });
            const assetMap = readJson(assetMapPath) as Record<string, string>;
            const mapped = assetMap[key];
            if (!mapped || !existsSync(mapped)) return sendJson(res, 404, { error: `asset not found: ${key}` });
            const ext = path.extname(mapped).toLowerCase();
            const type = ext === '.png' ? 'image/png' : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' : 'application/octet-stream';
            res.statusCode = 200;
            res.setHeader('Content-Type', type);
            res.setHeader('Cache-Control', 'public, max-age=60');
            createReadStream(mapped).pipe(res);
          } catch (error) {
            sendJson(res, 500, { error: (error as Error).message });
          }
          return;
        }

        if (url.pathname === '/api/f2/apply-m2' && req.method === 'POST') {
          if (!loopback) return sendJson(res, 403, { error: 'loopback only' });
          try {
            if (!existsSync(productPath) || !existsSync(assetMapPath)) {
              return sendJson(res, 503, {
                error: '本机 M2 冰箱夹具缺失',
                productPath,
                assetMapPath,
              });
            }
            mkdirSync(evidenceDir, { recursive: true });
            const mergedOut = path.join(evidenceDir, 'm2-merged.json');
            const previewOut = path.join(evidenceDir, 'm2-preview-scene.json');
            const { mergeSceneTemplate } = await import(mergeModule);
            const template = readJson(templatePath);
            const product = readJson(productPath);
            const { scene, newModelId } = mergeSceneTemplate({
              sceneTemplateData: template,
              singleSceneData: product,
              replaceId: REPLACE_ID_M2,
            });
            writeFileSync(mergedOut, JSON.stringify(scene));
            // Hide missing kitchen meshes for viewer/preview (same as prepare_preview_scene).
            const prep = spawnSync(process.execPath, [prepareModule, mergedOut, assetMapPath, previewOut, productPath, PRODUCT_VIEW, MERGED_VIEW], {
              encoding: 'utf8',
            });
            if (prep.status !== 0) {
              return sendJson(res, 500, { error: prep.stderr || 'prepare_preview_scene failed' });
            }
            const previewScene = readJson(previewOut);
            const assetMap = readJson(assetMapPath);
            sendJson(res, 200, {
              name: 'M2 冰箱厨房（本机夹具）',
              replaceId: REPLACE_ID_M2,
              newModelId,
              preferredViewId: MERGED_VIEW,
              scene: previewScene,
              assetMap,
              mergedPath: mergedOut,
              previewScenePath: previewOut,
              note: '官方壳 RF_Kitchen_0302 / ccdaa114 不在本机；厨房 mesh 已隐藏。',
            });
          } catch (error) {
            sendJson(res, 500, { error: (error as Error).message });
          }
          return;
        }

        if (url.pathname === '/api/f2/submit-final' && req.method === 'POST') {
          if (!loopback) return sendJson(res, 403, { error: 'loopback only' });
          try {
            const raw = await readBody(req);
            const body = JSON.parse(raw) as {
              scene: unknown;
              assetMap: Record<string, string>;
              viewId: string;
              name?: string;
              dryRun?: boolean;
              width?: number;
              height?: number;
              spp?: number;
              outName?: string;
            };
            mkdirSync(evidenceDir, { recursive: true });
            const stamp = Date.now();
            const scenePath = path.join(evidenceDir, `submit-scene-${stamp}.json`);
            const mapPath = path.join(evidenceDir, `submit-assets-${stamp}.json`);
            const outPath = path.join(evidenceDir, body.outName ?? `f2-final-${stamp}.png`);
            const logPath = path.join(evidenceDir, `submit-final-${stamp}.log`);
            writeFileSync(scenePath, JSON.stringify(body.scene));
            writeFileSync(mapPath, JSON.stringify(body.assetMap));
            const command = [
              'python3',
              blenderFinal,
              '--scene', scenePath,
              '--asset-map', mapPath,
              '--view', body.viewId,
              '--out', outPath,
              '--width', String(body.width ?? 640),
              '--height', String(body.height ?? 360),
              '--spp', String(body.spp ?? 4),
              '--denoise', '0',
            ];
            writeFileSync(logPath, `cwd=${repoRoot}\ncommand=${JSON.stringify(command)}\ndryRun=${!!body.dryRun}\n`);
            if (body.dryRun) {
              return sendJson(res, 200, {
                ok: true,
                dryRun: true,
                command,
                logPath,
                outPath,
                message: 'dry-run：已写入 scene/asset-map/命令，未启动 Blender',
              });
            }
            await new Promise<void>((resolve, reject) => {
              const child = spawn(command[0], command.slice(1), { cwd: repoRoot });
              let log = readFileSync(logPath, 'utf8');
              child.stdout.on('data', (d) => { log += d.toString(); writeFileSync(logPath, log); });
              child.stderr.on('data', (d) => { log += d.toString(); writeFileSync(logPath, log); });
              child.on('error', reject);
              child.on('close', (code) => {
                log += `\nexit=${code}\n`;
                writeFileSync(logPath, log);
                if (code === 0) resolve();
                else reject(new Error(`run_blender_final.py exit ${code}; see ${logPath}`));
              });
            });
            sendJson(res, 200, {
              ok: true,
              dryRun: false,
              command,
              logPath,
              outPath,
              message: `成片已写入 ${outPath}`,
            });
          } catch (error) {
            sendJson(res, 500, { error: (error as Error).message });
          }
          return;
        }

        next();
      });
    },
  };
}

export const F2_M2_REPLACE_ID = REPLACE_ID_M2;
