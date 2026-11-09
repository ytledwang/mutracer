#!/bin/bash
# M4 主链：选模板(M2 merge) → 导入 GLB → 薄参派生 → 多机位本机预览 → 可选云端成片(--cloud)
# 产物：out/m4-scene.json out/m4-assets.json out/m4-preview-<view8>.png [out/m4-cloud.png]
# 环境变量：GLB GLB_KEY GLB_POS GLB_SCALE VIEWS HDRI_BRIGHTNESS EXPOSURE WIDTH HEIGHT SPP SKIP_M2=1 CLOUD=1
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
M2="$ROOT/tools/scene-template"
FRIDGE="$ROOT/tools/cloud-service/poc-out/fridge"
[ "${1:-}" = "--cloud" ] && CLOUD=1
OUT="$HERE/out"; mkdir -p "$OUT"
export BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"

GLB="${GLB:-$ROOT/examples/assets/chess.glb}"          # 或 tools/import-smoke/out/{sample-fbx,box-stp}.glb
GLB_KEY="${GLB_KEY:-m4/import.glb}"
GLB_POS="${GLB_POS:-0.9,-1.2,0}"; GLB_SCALE="${GLB_SCALE:-0.6}"
VIEWS="${VIEWS:-298cfe60-923d-44fb-a0d1-f2206b9a48e1,3c697acc-1228-4e46-ba54-77eb7bb87cfb}"
HDRI_BRIGHTNESS="${HDRI_BRIGHTNESS:-1.2}"; EXPOSURE="${EXPOSURE:-1.0}"
WIDTH="${WIDTH:-640}"; HEIGHT="${HEIGHT:-360}"; SPP="${SPP:-16}"
PRODUCT="$FRIDGE/assets/customer_asset/1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a/scene.json"
MERGED_VIEW="1c4a3883-8668-4c16-a10e-0b7c24272279"

# 1. 选模板：复用 M2（SKIP_M2=1 或已有产物则复用）
if [ -z "${SKIP_M2:-}" ] || [ ! -f "$M2/out/m2-preview-scene.json" ]; then "$M2/run_m2_demo.sh" >&2; fi
# 2-3. 导入 + 薄参 + 多视角
node "$HERE/apply_thin_params.mjs" --scene "$M2/out/m2-preview-scene.json" --product "$PRODUCT" \
  --asset-map "$FRIDGE/stage-fridge-assets.json" --glb "$GLB" --glb-key "$GLB_KEY" \
  --glb-pos "$GLB_POS" --glb-scale "$GLB_SCALE" --views "$VIEWS" --base-view "$MERGED_VIEW" \
  --hdri-brightness "$HDRI_BRIGHTNESS" --exposure "$EXPOSURE" \
  --out-scene "$OUT/m4-scene.json" --out-map "$OUT/m4-assets.json"
# 4. 多机位预览（preview 轨不吃 light_scale；薄参走 scene 内 hdri_brightness / 相机 exposure）
python3 "$ROOT/tools/dual-track/run_dual_track.py" preview --scene "$OUT/m4-scene.json" \
  --asset-map "$OUT/m4-assets.json" --views "$VIEWS" --preview-out "$OUT/m4-preview.png" \
  --preview-width "$WIDTH" --preview-height "$HEIGHT" --preview-spp "$SPP" >&2
# 5. 云端
if [ -n "${CLOUD:-}" ]; then "$HERE/submit_cloud_ssh.sh" || echo "CLOUD_FAILED (see M4-PROGRESS.md gap)" >&2; fi
echo "DONE_M4 scene=$OUT/m4-scene.json previews=$(ls "$OUT"/m4-preview-*.png | tr '\n' ' ')${CLOUD:+cloud=$OUT/m4-cloud.png}"
