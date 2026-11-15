#!/usr/bin/env bash
# STEP -> STL (gmsh) -> GLB (official preset) -> contract validate.
# Usage: convert_stp_to_glb.sh in.stp|in.step|in.stl [out.glb]
# Missing materials or no mm→m conversion fail or warn explicitly; the output
# is renamed to *.rejected.glb on contract failure (not a silent bad GLB).
# Set CONTRACT_ALLOW_NO_MATERIAL=1 to downgrade missing-material to a warning.
# Making STP materials + mm→m a sellable conversion is a known gap, not this script's job.
# gmsh: `gmsh` on PATH, else the gmsh Python module of $GMSH_PYTHON (default python3).
set -euo pipefail
IN="${1:?usage: $0 in.stp [out.glb]}"
OUT="${2:-${IN%.*}.glb}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PRESET="$ROOT/tools/import-contract/export_glb_preset.py"
VALIDATE="$ROOT/tools/import-contract/validate_glb.py"
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
"$BLENDER" --background --python "$PRESET" -- --input "$STL" --output "$OUT" --importer stl \
  >"${OUT%.glb}.blender.log" 2>&1 || { tail -20 "${OUT%.glb}.blender.log" >&2; exit 1; }
[ "$(head -c 4 "$OUT")" = glTF ] || { echo "not a GLB: $OUT" >&2; exit 1; }

validate_args=("$OUT" --source-units mm --unit-scale 1)
if [ -n "${CONTRACT_ALLOW_NO_MATERIAL:-}" ]; then
  validate_args+=(--allow-missing-materials)
fi
set +e
python3 "$VALIDATE" "${validate_args[@]}"
status=$?
set -e
if [ "$status" -ne 0 ]; then
  rejected="${OUT%.glb}.rejected.glb"
  mv -f "$OUT" "$rejected"
  echo "contract failed (exit $status); moved output to $rejected" >&2
  echo "STP gap: this path has no materials from gmsh and does not convert mm→m. That is a known gap, not a silent success." >&2
  exit "$status"
fi
echo "$OUT OK ($(wc -c <"$OUT" | tr -d ' ') bytes, glTF magic, contract checked)"
