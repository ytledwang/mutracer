#!/usr/bin/env bash
# FBX -> GLB through Blender. Usage: convert_fbx_to_glb.sh in.fbx [out.glb]
set -euo pipefail
IN="${1:?usage: $0 in.fbx [out.glb]}"
OUT="${2:-${IN%.*}.glb}"
BLENDER="${BLENDER:-$(command -v blender || echo /Applications/Blender.app/Contents/MacOS/Blender)}"
IN="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
mkdir -p "$(dirname "$OUT")"; OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
rm -f "$OUT"
"$BLENDER" --background --python-expr "
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=r'''$IN''')
bpy.ops.export_scene.gltf(filepath=r'''$OUT''', export_format='GLB')
" >"${OUT%.glb}.blender.log" 2>&1 || { tail -20 "${OUT%.glb}.blender.log" >&2; exit 1; }
[ "$(head -c 4 "$OUT")" = glTF ] || { echo "not a GLB: $OUT" >&2; exit 1; }
echo "$OUT OK ($(wc -c <"$OUT" | tr -d ' ') bytes, glTF magic)"
