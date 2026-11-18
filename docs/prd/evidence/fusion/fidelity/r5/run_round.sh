#!/bin/zsh
# usage: run_round.sh NAME [--best CHECKJSON] -- <extra run_blender_final args>
set -u
cd /Users/wangjianzheng/Project/git/mutracer
R5=docs/prd/evidence/fusion/fidelity/r5
NAME=$1; shift; BEST=()
if [ "$1" = "--best" ]; then BEST=(--best $2); shift 2; fi
[ "$1" = "--" ] && shift
OUT=$R5/render-$NAME.png
{ echo "START $(date '+%Y-%m-%d %H:%M:%S %z') Asia/Shanghai"; echo "ARGS $*";
  python3 tools/dual-track/blender/run_blender_final.py --scene $R5/scene-gold329c-preview.json \
    --asset-map docs/prd/evidence/fusion/fidelity/r3/official-assets.json --out $PWD/$OUT \
    --view 298cfe60-923d-44fb-a0d1-f2206b9a48e1 --width 1920 --height 1080 --spp 128 --denoise 1 \
    --view-transform Standard "$@"; echo "EXIT $?"; echo "END $(date '+%Y-%m-%d %H:%M:%S %z') Asia/Shanghai"; } > $R5/render-$NAME.log 2>&1
grep -q '^EXIT 0' $R5/render-$NAME.log || { echo "RENDER_FAILED"; tail -20 $R5/render-$NAME.log; exit 3; }
(cd $R5 && shasum -a 256 render-$NAME.png > render-$NAME.png.sha256)
python3 - "$NAME" "$*" <<'PY'
import json,sys
json.dump({"round":sys.argv[1],"scene":"docs/prd/evidence/fusion/fidelity/r5/scene-gold329c-preview.json (gold task 329c202e scene_json, hidden 0)",
 "view":"298cfe60 Front / camera 858db55c (gold post gamma 0.9 contrast 1.2 exposure 0.8 saturation 0.8)",
 "base_cli":"run_blender_final.py --spp 128 --denoise 1 --width 1920 --height 1080 --view-transform Standard","extra_cli":sys.argv[2],
 "blender_inner_sha256":"9ba254656e29469bf33bc47248cd3ab16ba0aee5fe862c272ca411866d4c9436","replace_id":"ccdaa114-cdb7-4ef5-af26-022938a780d5",
 "m2_id_not_used":"c83a2f4a-0a3d-4494-8da9-37e6ca6943a7","no_new_pulls":True},open(f"docs/prd/evidence/fusion/fidelity/r5/params-{sys.argv[1]}.json","w"),indent=1)
PY
python3 tools/fusion-checks/fidelity_r4_check.py $OUT $R5/params-$NAME.json $R5/check-$NAME.json --inner-sha 9ba254656e29469bf33bc47248cd3ab16ba0aee5fe862c272ca411866d4c9436 --evidence-dir $R5 $BEST
C=$?; echo "CHECK_EXIT $C"
python3 tools/fusion-checks/fidelity_r4_analyze.py docs/prd/evidence/fusion/fidelity/r2/reference-fridge-ref-front-329c-1920.png $OUT $R5/region-stats-$NAME.json | sed -n '2,20p'
exit $C
