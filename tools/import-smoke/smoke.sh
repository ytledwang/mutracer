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

echo "== 3. STL -> GLB via official preset + contract check"
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
PRESET="$ROOT/tools/import-contract/export_glb_preset.py"
VALIDATE="$ROOT/tools/import-contract/validate_glb.py"
rm -f "$OUT/cube.glb"
"$BLENDER" --background --python "$PRESET" -- --input "$OUT/cube.stl" --output "$OUT/cube.glb" --importer stl >"$OUT/blender-stl.log" 2>&1
head -c 4 "$OUT/cube.glb" | grep -q glTF && echo "cube.glb wrote $(wc -c <"$OUT/cube.glb") bytes"
set +e
python3 "$VALIDATE" "$OUT/cube.glb"
cube_status=$?
set -e
if [ "$cube_status" -eq 0 ]; then
  echo "FAIL: cube.glb has no materials but contract exited 0" >&2
  exit 1
fi
echo "OK: cube.glb contract rejected as expected (exit $cube_status)"

HERE="$ROOT/tools/import-smoke"
echo "== 4. FBX -> GLB (fixtures/sample.fbx) via official preset + validate"
BLENDER="$BLENDER" "$HERE/convert_fbx_to_glb.sh" "$HERE/fixtures/sample.fbx" "$OUT/sample-fbx.glb"

echo "== 5. STEP -> STL -> GLB (fixtures/box.step); contract must not silently accept a bad file"
if command -v gmsh >/dev/null || "${GMSH_PYTHON:-python3}" -c "import gmsh" 2>/dev/null; then
  rm -f "$OUT/box-stp.glb" "$OUT/box-stp.rejected.glb"
  set +e
  BLENDER="$BLENDER" "$HERE/convert_stp_to_glb.sh" "$HERE/fixtures/box.step" "$OUT/box-stp.glb"
  stp_status=$?
  set -e
  if [ "$stp_status" -eq 0 ]; then
    echo "FAIL: STP convert exited 0 on a material-less, unscaled mm cube" >&2
    exit 1
  fi
  if [ ! -f "$OUT/box-stp.rejected.glb" ]; then
    echo "FAIL: expected $OUT/box-stp.rejected.glb after contract failure" >&2
    exit 1
  fi
  echo "OK: STP contract rejected box.step (exit $stp_status), wrote box-stp.rejected.glb"
else
  echo "SKIPPED: no gmsh"
fi

echo "== 6. import-contract fixtures: good PASS, bad FAIL"
GOOD="$ROOT/tools/import-contract/fixtures/good-named-pivot.glb"
BAD="$ROOT/tools/import-contract/fixtures/bad-flattened-palette.glb"
python3 "$VALIDATE" "$GOOD" --require-pivot --require-camera --expect-pivot Door_Pivot --placeholder f1-named-pivot-placeholder
set +e
python3 "$VALIDATE" "$BAD" --require-pivot --expect-pivot Door_Pivot --placeholder f1-named-pivot-placeholder
bad_status=$?
set -e
if [ "$bad_status" -eq 0 ]; then
  echo "FAIL: bad fixture was accepted" >&2
  exit 1
fi
echo "OK: bad fixture rejected (exit $bad_status)"
