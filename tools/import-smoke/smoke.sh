#!/usr/bin/env bash
# M3 import smoke: GLB direct render + STL->GLB (the Blender half of the STP chain).
# Usage: tools/import-smoke/smoke.sh   (run from anywhere)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/tools/import-smoke/out"
BIN="${MUTRACER_RENDER_BIN:-$ROOT/native/host/target/release/mutracer-render}"
BLENDER="${BLENDER:-$(command -v blender || echo /Applications/Blender.app/Contents/MacOS/Blender)}"
mkdir -p "$OUT"

echo "== 1. GLB direct: examples/assets/chess.glb -> mutracer-render"
"$BIN" --scene "$ROOT/tools/cloud-service/poc-out/scene.json" \
  --asset-map "$ROOT/tools/cloud-service/poc-out/assets.json" \
  --out "$OUT/chess-256-lookat.png" --camera-mode lookat \
  --width 256 --height 256 --samples 16 --bounces 3 --denoise 0 \
  --camera-target 0,0,0 --light-scale 1 --timeout-ms 120000
python3 - "$OUT/chess-256-lookat.png" <<'P'
import sys
from PIL import Image
px = list(Image.open(sys.argv[1]).convert("RGB").getdata())
n = len(set(px))
print("unique colors:", n)
sys.exit(0 if n > 100 else "blank render")
P

echo "== 2. gmsh availability (STP->STL step)"
if command -v gmsh >/dev/null; then
  echo "gmsh found: $(command -v gmsh)"
elif "${GMSH_PYTHON:-python3}" -c "import gmsh" 2>/dev/null; then
  echo "gmsh Python module found via ${GMSH_PYTHON:-python3}"
else
  echo "gmsh NOT FOUND -> step 5 is skipped (set GMSH_PYTHON to a venv with 'pip install gmsh')"
fi

echo "== 3. STL -> GLB via Blender (same bpy calls as cloud-relay.py)"
cat > "$OUT/cube.stl" <<'S'
solid cube
facet normal 0 0 -1
outer loop
vertex 0 0 0
vertex 1 1 0
vertex 1 0 0
endloop
endfacet
facet normal 0 0 -1
outer loop
vertex 0 0 0
vertex 0 1 0
vertex 1 1 0
endloop
endfacet
facet normal 0 0 1
outer loop
vertex 0 0 1
vertex 1 0 1
vertex 1 1 1
endloop
endfacet
facet normal 0 0 1
outer loop
vertex 0 0 1
vertex 1 1 1
vertex 0 1 1
endloop
endfacet
facet normal 0 -1 0
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 1 0 1
endloop
endfacet
facet normal 0 -1 0
outer loop
vertex 0 0 0
vertex 1 0 1
vertex 0 0 1
endloop
endfacet
facet normal 1 0 0
outer loop
vertex 1 0 0
vertex 1 1 0
vertex 1 1 1
endloop
endfacet
facet normal 1 0 0
outer loop
vertex 1 0 0
vertex 1 1 1
vertex 1 0 1
endloop
endfacet
facet normal 0 1 0
outer loop
vertex 1 1 0
vertex 0 1 0
vertex 0 1 1
endloop
endfacet
facet normal 0 1 0
outer loop
vertex 1 1 0
vertex 0 1 1
vertex 1 1 1
endloop
endfacet
facet normal -1 0 0
outer loop
vertex 0 1 0
vertex 0 0 0
vertex 0 0 1
endloop
endfacet
facet normal -1 0 0
outer loop
vertex 0 1 0
vertex 0 0 1
vertex 0 1 1
endloop
endfacet
endsolid cube
S
rm -f "$OUT/cube.glb"
"$BLENDER" --background --python-expr "import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.wm.stl_import(filepath=r'$OUT/cube.stl'); bpy.ops.export_scene.gltf(filepath=r'$OUT/cube.glb', export_format='GLB')" >"$OUT/blender-stl.log" 2>&1
head -c 4 "$OUT/cube.glb" | grep -q glTF && echo "cube.glb OK ($(wc -c <"$OUT/cube.glb") bytes)"

HERE="$ROOT/tools/import-smoke"
echo "== 4. FBX -> GLB (fixtures/sample.fbx)"
BLENDER="$BLENDER" "$HERE/convert_fbx_to_glb.sh" "$HERE/fixtures/sample.fbx" "$OUT/sample-fbx.glb"

echo "== 5. STEP -> STL -> GLB (fixtures/box.step)"
if command -v gmsh >/dev/null || "${GMSH_PYTHON:-python3}" -c "import gmsh" 2>/dev/null; then
  BLENDER="$BLENDER" "$HERE/convert_stp_to_glb.sh" "$HERE/fixtures/box.step" "$OUT/box-stp.glb"
else
  echo "SKIPPED: no gmsh"
fi
