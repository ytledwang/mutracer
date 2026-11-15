#!/bin/zsh
# r7 acceptance: (1) ue55 unit test, (2) default path identity vs pre-r5 code,
# (3) fidelity_r4_check on a candidate render. Exit 0 only if all pass and the
# candidate beats the best so far; 1 = not improved; 2 = integrity failure.
# usage: fidelity_r7_check.sh CANDIDATE.png PARAMS.json OUT.json [--best PREV.json]
set -u
cd /Users/wangjianzheng/Project/git/mutracer
R7=docs/prd/evidence/fusion/fidelity/r7
python3 tools/fusion-checks/test_ue55_post.py || { echo "FAIL: ue55 unit test"; exit 2; }
ID=$R7/default-identity
[ -f $ID/probe-state.json ] && [ -f $ID/probe-post.png ] || { echo "FAIL: default identity probe not run"; exit 2; }
[ "$(shasum -a 256 $ID/probe-state.json | cut -d' ' -f1)" = 367c8c93504e19939f6ef7d0c5522291593b3d97df627352d4a7b406b5a56c96 ] || { echo "FAIL: default scene state changed"; exit 2; }
[ "$(shasum -a 256 $ID/probe-post.png | cut -d' ' -f1)" = 024e98431d937525845ad2cbf88455a3fadbc55b641f2636b9d3cc0db72143e4 ] || { echo "FAIL: default post output changed"; exit 2; }
[ "$(cat $ID/probe-inner.sha256)" = "$(shasum -a 256 tools/dual-track/blender/blender_inner.py | cut -d' ' -f1)" ] || { echo "FAIL: identity probe is stale for current blender_inner.py"; exit 2; }
python3 tools/fusion-checks/fidelity_r4_check.py "$1" "$2" "$3" --inner-sha "$(cat $ID/probe-inner.sha256)" --evidence-dir $R7 "${@:4}"
