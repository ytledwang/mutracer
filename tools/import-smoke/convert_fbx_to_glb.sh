#!/usr/bin/env bash
# FBX -> GLB through the official import-contract preset, then validate.
# Usage: convert_fbx_to_glb.sh in.fbx [out.glb]
set -euo pipefail
IN="${1:?usage: $0 in.fbx [out.glb]}"
OUT="${2:-${IN%.*}.glb}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PRESET="$ROOT/tools/import-contract/export_glb_preset.py"
VALIDATE="$ROOT/tools/import-contract/validate_glb.py"
BLENDER="${BLENDER:-$(command -v blender || echo /Applications/Blender.app/Contents/MacOS/Blender)}"
IN="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
mkdir -p "$(dirname "$OUT")"; OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
rm -f "$OUT"
"$BLENDER" --background --python "$PRESET" -- --input "$IN" --output "$OUT" --importer fbx \
  >"${OUT%.glb}.blender.log" 2>&1 || { tail -20 "${OUT%.glb}.blender.log" >&2; exit 1; }
[ "$(head -c 4 "$OUT")" = glTF ] || { echo "not a GLB: $OUT" >&2; exit 1; }
python3 "$VALIDATE" "$OUT"
echo "$OUT OK ($(wc -c <"$OUT" | tr -d ' ') bytes, glTF magic, contract checked)"
