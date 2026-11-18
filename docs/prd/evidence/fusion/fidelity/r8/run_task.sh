#!/bin/zsh
# usage: run_task.sh SHORTNAME SCENE VIEW GOLD_1920 EXPECTED_ANGLE -- <locked flags...>
set -u
cd /Users/wangjianzheng/Project/git/mutracer
R8=docs/prd/evidence/fusion/fidelity/r8
NAME=$1 SCENE=$2 VIEW=$3 GOLD=$4 ANGLE=$5; shift 5
[ "$1" = "--" ] && shift
OUT=$R8/render-$NAME.png
{ echo "START $(date '+%Y-%m-%d %H:%M:%S %z') Asia/Shanghai"; echo "ARGS $*";
  python3 tools/dual-track/blender/run_blender_final.py --scene $SCENE \
    --asset-map ${ASSET_MAP:-docs/prd/evidence/fusion/fidelity/r8/assets.json} --out $PWD/$OUT \
    --view $VIEW --width 1920 --height 1080 --spp 256 --denoise 1 \
    --view-transform Standard "$@"; echo "EXIT $?"; echo "END $(date '+%Y-%m-%d %H:%M:%S %z') Asia/Shanghai"; } > $R8/render-$NAME.log 2>&1
grep -q '^EXIT 0' $R8/render-$NAME.log || { echo "RENDER_FAILED"; tail -30 $R8/render-$NAME.log; exit 3; }
(cd $R8 && shasum -a 256 render-$NAME.png > render-$NAME.png.sha256)
echo "RENDER_OK $NAME"
