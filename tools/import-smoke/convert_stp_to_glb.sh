#!/usr/bin/env bash
# STEP -> STL (gmsh) -> GLB (Blender), same chain as tools/cloud-relay.py.
# Usage: convert_stp_to_glb.sh in.stp|in.step|in.stl [out.glb]
# gmsh: `gmsh` on PATH, else the gmsh Python module of $GMSH_PYTHON (default python3). Setup: python3 -m venv .venv-gmsh && .venv-gmsh/bin/pip install gmsh
set -euo pipefail
IN="${1:?usage: $0 in.stp [out.glb]}"
OUT="${2:-${IN%.*}.glb}"
BLENDER="${BLENDER:-$(command -v blender || echo /Applications/Blender.app/Contents/MacOS/Blender)}"
IN="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
mkdir -p "$(dirname "$OUT")"; OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
STL="${OUT%.glb}.stl"
case "$IN" in
  *.stl|*.STL) STL="$IN" ;;
  *)
    if command -v gmsh >/dev/null; then
      gmsh -3 "$IN" -format stl -o "$STL" -v 1
    else
      "${GMSH_PYTHON:-python3}" - "$IN" "$STL" <<'P'
import sys
try:
    import gmsh
except ImportError:
    sys.exit("gmsh not found: pip install gmsh (or brew install gmsh), or pass a pre-meshed .stl")
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
gmsh.open(sys.argv[1]); gmsh.model.mesh.generate(2)
gmsh.write(sys.argv[2]); gmsh.finalize()
P
    fi ;;
esac
rm -f "$OUT"
"$BLENDER" --background --python-expr "
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.stl_import(filepath=r'''$STL''')
bpy.ops.export_scene.gltf(filepath=r'''$OUT''', export_format='GLB')
" >"${OUT%.glb}.blender.log" 2>&1 || { tail -20 "${OUT%.glb}.blender.log" >&2; exit 1; }
[ "$(head -c 4 "$OUT")" = glTF ] || { echo "not a GLB: $OUT" >&2; exit 1; }
echo "$OUT OK ($(wc -c <"$OUT" | tr -d ' ') bytes, glTF magic)"
