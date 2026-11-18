#!/bin/zsh
# usage: probe_render.sh NAME W H SPP -- <extra run_blender_final args>; writes linear EXR -> npy (no check)
set -u
cd /Users/wangjianzheng/Project/git/mutracer
R7=docs/prd/evidence/fusion/fidelity/r7; NAME=$1 W=$2 H=$3 SPP=$4; shift 4; [ "$1" = "--" ] && shift
S=$HOME/mutracer-scratch/r7
{ echo "START $(date '+%Y-%m-%d %H:%M:%S %z') Asia/Shanghai"; echo "ARGS $*";
  python3 tools/dual-track/blender/run_blender_final.py --scene docs/prd/evidence/fusion/fidelity/r5/scene-gold329c-preview.json \
    --asset-map docs/prd/evidence/fusion/fidelity/r3/official-assets.json --out $S/$NAME.png \
    --view 298cfe60-923d-44fb-a0d1-f2206b9a48e1 --width $W --height $H --spp $SPP --denoise 1 \
    --view-transform Standard --linear-out $S/$NAME.exr "$@"; echo "EXIT $?"; echo "END $(date '+%Y-%m-%d %H:%M:%S %z') Asia/Shanghai"; } > $R7/probes/$NAME.log 2>&1
grep -q '^EXIT 0' $R7/probes/$NAME.log || { echo RENDER_FAILED; tail -20 $R7/probes/$NAME.log; exit 3; }
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python $HOME/mutracer-scratch/exr2npy.py -- $S/$NAME.exr $S/$NAME.npy >/dev/null 2>&1 || { echo NPY_FAILED; exit 3; }
echo "OK $NAME"
