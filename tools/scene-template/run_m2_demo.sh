#!/bin/bash
# M2 一键：模板 + 单品 --replace_id 合并 → 本机 mutracer-render 预览。
# 产物：out/m2-merged.json（合并 scene）、out/m2-preview-scene.json（预览派生）、out/m2-preview.png
# 可用环境变量覆盖：TEMPLATE PRODUCT REPLACE_ID ASSET_MAP PRODUCT_VIEW MERGED_VIEW WIDTH HEIGHT SPP
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FRIDGE="$ROOT/tools/cloud-service/poc-out/fridge"

TEMPLATE="${TEMPLATE:-$HERE/fixtures/real/template-fridge-kitchen.json}"
PRODUCT="${PRODUCT:-$FRIDGE/assets/customer_asset/1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a/scene.json}"
REPLACE_ID="${REPLACE_ID:-c83a2f4a-0a3d-4494-8da9-37e6ca6943a7}"
ASSET_MAP="${ASSET_MAP:-$FRIDGE/stage-fridge-assets.json}"
PRODUCT_VIEW="${PRODUCT_VIEW:-298cfe60-923d-44fb-a0d1-f2206b9a48e1}"
MERGED_VIEW="${MERGED_VIEW:-1c4a3883-8668-4c16-a10e-0b7c24272279}"
WIDTH="${WIDTH:-640}"; HEIGHT="${HEIGHT:-360}"; SPP="${SPP:-16}"

OUT="$HERE/out"
MERGED="$OUT/m2-merged.json"
PREVIEW_SCENE="$OUT/m2-preview-scene.json"
PREVIEW="$OUT/m2-preview.png"
mkdir -p "$OUT"

node "$HERE/merge_scene_template.mjs" --template "$TEMPLATE" --product "$PRODUCT" \
  --replace-id "$REPLACE_ID" --out "$MERGED"
node "$HERE/prepare_preview_scene.mjs" "$MERGED" "$ASSET_MAP" "$PREVIEW_SCENE" \
  "$PRODUCT" "$PRODUCT_VIEW" "$MERGED_VIEW"
python3 "$ROOT/tools/dual-track/run_dual_track.py" preview \
  --scene "$PREVIEW_SCENE" --asset-map "$ASSET_MAP" --view "$MERGED_VIEW" \
  --preview-out "$PREVIEW" --preview-width "$WIDTH" --preview-height "$HEIGHT" \
  --preview-spp "$SPP" >&2

echo "DONE_M2 merge=$MERGED preview=$PREVIEW"
