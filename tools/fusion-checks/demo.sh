#!/usr/bin/env bash
# Friday main-chain demo (local M2 fixture, no official kitchen shell).
# Import → validate (bad files must not succeed silently) → editor evidence (F2 r2b)
# → apply template → realtime/quality (F2 r2b) → 提交渲染 one image per merged view.
# Exits 1 if any item fails; every item is still recorded. Never git add / commit / push.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
EV="$ROOT/docs/prd/evidence/fusion/demo"
F2EV="$ROOT/docs/prd/evidence/fusion/f2/r2b"
mkdir -p "$EV" "$EV/ui"
LOG="$EV/demo.sh.log"
REPORT="$EV/demo-report.json"
: > "$LOG"
pass=0
fail=0
declare -a ITEMS=()

record() {
  local status="$1" name="$2" code="$3" cmd="$4" extra="${5:-}"
  ITEMS+=("$status|$name|$code|$cmd|$extra")
  if [[ "$status" == PASS ]]; then pass=$((pass+1)); else fail=$((fail+1)); fi
  echo "$status  $name  exit=$code  $extra" | tee -a "$LOG"
}

run_ok() {
  local name="$1"; shift
  local cmd="$*"
  echo "+ $cmd" | tee -a "$LOG"
  set +e
  eval "$cmd" >>"$LOG" 2>&1
  local code=$?
  set -u
  if [[ $code -eq 0 ]]; then record PASS "$name" "$code" "$cmd"; else record FAIL "$name" "$code" "$cmd"; fi
}

# A step that is supposed to fail (bad GLB / rejected STP). PASS if exit != 0.
run_expect_fail() {
  local name="$1"; shift
  local cmd="$*"
  echo "+ $cmd  (expect non-zero)" | tee -a "$LOG"
  set +e
  eval "$cmd" >>"$LOG" 2>&1
  local code=$?
  set -u
  if [[ $code -ne 0 ]]; then record PASS "$name" "$code" "$cmd" "expected-nonzero"; else record FAIL "$name" "$code" "$cmd" "should-have-failed"; fi
}

VALIDATE="python3 tools/import-contract/validate_glb.py"
GOOD="tools/import-contract/fixtures/good-named-pivot.glb"
BAD="tools/import-contract/fixtures/bad-flattened-palette.glb"
STP="tools/import-smoke/fixtures/box.step"
VALFLAGS="--require-pivot --require-camera --expect-pivot Door_Pivot --placeholder f1-named-pivot-placeholder"

set +e
python3 tools/import-contract/validate_glb.py $GOOD $VALFLAGS >"$EV/validate-good.log" 2>&1
code=$?
set -u
if [[ $code -eq 0 ]]; then record PASS "import: validate good GLB" "$code" "validate_glb.py good-named-pivot.glb" "$EV/validate-good.log"
else record FAIL "import: validate good GLB" "$code" "validate_glb.py good-named-pivot.glb" "$EV/validate-good.log"; fi

set +e
python3 tools/import-contract/validate_glb.py $BAD --require-pivot --expect-pivot Door_Pivot --placeholder f1-named-pivot-placeholder >"$EV/validate-bad.log" 2>&1
code=$?
set -u
if [[ $code -ne 0 ]]; then record PASS "import: bad GLB rejected (not silent)" "$code" "validate_glb.py bad-flattened-palette.glb" "$EV/validate-bad.log"
else record FAIL "import: bad GLB rejected (not silent)" "$code" "validate_glb.py bad-flattened-palette.glb" "$EV/validate-bad.log"; fi

# STP convert then validate; must not silently succeed.
set +e
bash tools/import-smoke/convert_stp_to_glb.sh "$STP" "$EV/box-stp.glb" >"$EV/convert-stp.log" 2>&1
code=$?
set -u
if [[ $code -ne 0 && -f "$EV/box-stp.rejected.glb" ]]; then
  record PASS "import: STP convert+validate rejects bad output" "$code" "convert_stp_to_glb.sh box.step" "$EV/convert-stp.log;$EV/box-stp.rejected.glb"
elif [[ $code -ne 0 ]]; then
  record PASS "import: STP convert+validate rejects bad output" "$code" "convert_stp_to_glb.sh box.step" "$EV/convert-stp.log (no rejected.glb name, but failed)"
else
  record FAIL "import: STP convert+validate rejects bad output" "$code" "convert_stp_to_glb.sh box.step" "silent success would be a bug; see $EV/convert-stp.log"
fi

# Merge M2 (replace_id must stay c83a2f4a-…)
TEMPLATE="tools/scene-template/fixtures/real/template-fridge-kitchen.json"
PRODUCT="tools/cloud-service/poc-out/fridge/assets/customer_asset/1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a/scene.json"
REPLACE="c83a2f4a-0a3d-4494-8da9-37e6ca6943a7"
ASSETMAP="tools/cloud-service/poc-out/fridge/stage-fridge-assets.json"
set +e
node tools/scene-template/merge_scene_template.mjs \
  --template "$TEMPLATE" --product "$PRODUCT" --replace-id "$REPLACE" \
  --out "$EV/m2-merged.json" >"$EV/merge.log" 2>&1
code=$?
set -u
if [[ $code -eq 0 ]]; then record PASS "merge M2 template (replace_id c83a2f4a-…)" "$code" "merge_scene_template.mjs" "$EV/merge.log"
else record FAIL "merge M2 template (replace_id c83a2f4a-…)" "$code" "merge_scene_template.mjs" "$EV/merge.log"; fi

PRODUCT_VIEW="298cfe60-923d-44fb-a0d1-f2206b9a48e1"
MERGED_VIEW="1c4a3883-8668-4c16-a10e-0b7c24272279"
set +e
node tools/scene-template/prepare_preview_scene.mjs \
  "$EV/m2-merged.json" "$ASSETMAP" "$EV/m2-preview-scene.json" \
  "$PRODUCT" "$PRODUCT_VIEW" "$MERGED_VIEW" >"$EV/prepare.log" 2>&1
code=$?
set -u
if [[ $code -eq 0 ]]; then record PASS "prepare preview scene (hide missing kitchen meshes)" "$code" "prepare_preview_scene.mjs" "$EV/prepare.log"
else record FAIL "prepare preview scene (hide missing kitchen meshes)" "$code" "prepare_preview_scene.mjs" "$EV/prepare.log"; fi

# UI evidence from F2 r2b (headed Chrome / real GPU), copied into the demo package.
if [[ -f "$F2EV/f2-ui-report.json" ]]; then
  python3 - "$F2EV" "$EV" <<'PY'
import json, shutil, sys
from pathlib import Path
src, dest = Path(sys.argv[1]), Path(sys.argv[2])
ui = dest / "ui"
ui.mkdir(parents=True, exist_ok=True)
report = json.loads((src / "f2-ui-report.json").read_text())
failed = [i for i in report.get("items") or [] if i.get("status") != "PASS"]
copies = [
  "f1-named-materials-realtime-r2.png",
  "f1-named-materials-picked-r2.png",
  "f2-realtime-after-template-r2.png",
  "f2-quality-after-template-r2.png",
  "f2-front-realtime-r2.png",
  "f2-front-quality-r2.png",
  "f2-closeup-realtime-r2.png",
  "f2-closeup-quality-r2.png",
  "f2-orbit-timing-r2.json",
  "f2-ui-report.json",
]
for name in copies:
    p = src / name
    if p.exists():
        shutil.copy2(p, ui / name)
open(dest / "ui-source.txt", "w").write(
    f"UI steps (import visible, pick by name, apply template, realtime/quality) verified by tools/fusion-checks/f2_check.mjs\n"
    f"evidence: {src}\nlaunch={report.get('launchMode')} headedOnRealGpu={report.get('headedOnRealGpu')}\n"
    f"items={len(report.get('items') or [])} failed={len(failed)}\n"
)
sys.exit(1 if failed else 0)
PY
  code=$?
  if [[ $code -eq 0 ]]; then record PASS "UI chain evidence (F2 r2b, headed Chrome Metal)" "$code" "f2_check.mjs (r2b)" "$EV/ui"
  else record FAIL "UI chain evidence (F2 r2b, headed Chrome Metal)" "$code" "f2_check.mjs (r2b)" "$EV/ui"; fi
else
  record FAIL "UI chain evidence (F2 r2b, headed Chrome Metal)" "1" "missing $F2EV/f2-ui-report.json" "run f2_check.sh first"
fi

# 提交渲染: one image per merged view, local Blender, Standard view_transform (untouched).
python3 - "$EV" <<'PY' >"$EV/views.json"
import json, sys
from pathlib import Path
ev = Path(sys.argv[1])
scene = json.loads((ev / "m2-preview-scene.json").read_text())
views = []
for vid, v in (scene.get("views") or {}).items():
    cam = (scene.get("cameras") or {}).get(v.get("active_camera") or "", {})
    views.append({"id": vid, "name": v.get("name") or vid[:8], "camera": cam.get("name")})
print(json.dumps(views, ensure_ascii=False, indent=2))
PY

i=0
while IFS= read -r line; do
  # parsed below with python for safety
  true
done < /dev/null

set +e
python3 - "$ROOT" "$EV" "$ASSETMAP" <<'PY'
import json, subprocess, sys, re
from pathlib import Path
root, ev, assetmap = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
views = json.loads((ev / "views.json").read_text())
used = {}
results = []
for view in views:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", view["name"]).strip("-") or "view"
    key = slug
    used[key] = used.get(key, 0) + 1
    if used[key] > 1:
        slug = f"{slug}-{used[key]}"
    out = ev / f"final-{slug}-{view['id'][:8]}.png"
    log = ev / f"final-{slug}-{view['id'][:8]}.log"
    cmd = [
        "python3", str(root / "tools/dual-track/blender/run_blender_final.py"),
        "--scene", str(ev / "m2-preview-scene.json"),
        "--asset-map", str(root / assetmap) if not Path(assetmap).is_absolute() else assetmap,
        "--view", view["id"],
        "--out", str(out),
        "--width", "640", "--height", "360", "--spp", "4", "--denoise", "0",
    ]
    with log.open("w") as fh:
        fh.write("command=" + json.dumps(cmd) + "\n")
        proc = subprocess.run(cmd, cwd=root, stdout=fh, stderr=subprocess.STDOUT)
    results.append({
        "id": view["id"], "name": view["name"], "camera": view.get("camera"),
        "out": str(out), "log": str(log), "exit": proc.returncode, "exists": out.is_file(),
    })
    print(f"{'PASS' if proc.returncode==0 and out.is_file() else 'FAIL'}  submit {view['name']} {view['id'][:8]} exit={proc.returncode} {out}")
(ev / "final-views-results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
sys.exit(0 if all(r["exit"]==0 and r["exists"] for r in results) else 1)
PY
code=$?
set -u
if [[ $code -eq 0 ]]; then record PASS "submit render: one final per merged view (spp=4, local Blender)" "$code" "run_blender_final.py --spp 4" "$EV/final-views-results.json"
else record FAIL "submit render: one final per merged view (spp=4, local Blender)" "$code" "run_blender_final.py --spp 4" "$EV/final-views-results.json"; fi

# Write report
python3 - "$REPORT" "$pass" "$fail" <<'PY' "${ITEMS[@]}"
import json, sys
report_path, passed, failed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
items = []
for raw in sys.argv[4:]:
    parts = raw.split("|", 4)
    while len(parts) < 5:
        parts.append("")
    status, name, code, cmd, extra = parts
    items.append({"status": status, "name": name, "exit": int(code or 0), "command": cmd, "extra": extra})
# The ITEMS are passed after the heredoc in bash? This approach is fragile.
# We'll write the report from bash instead.
print("skip")
PY

{
  echo "{"
  echo "  \"pass\": $pass,"
  echo "  \"fail\": $fail,"
  echo "  \"evidence\": \"$EV\","
  echo "  \"items\": ["
  first=1
  for row in "${ITEMS[@]}"; do
    IFS='|' read -r status name code cmd extra <<<"$row"
    if [[ $first -eq 0 ]]; then echo ","; fi
    first=0
    python3 -c 'import json,sys; print("    "+json.dumps({"status":sys.argv[1],"name":sys.argv[2],"exit":int(sys.argv[3]),"command":sys.argv[4],"extra":sys.argv[5]},ensure_ascii=False), end="")' \
      "$status" "$name" "$code" "$cmd" "$extra"
  done
  echo
  echo "  ]"
  echo "}"
} > "$REPORT"

echo
echo "Demo summary: pass=$pass fail=$fail  report=$REPORT"
if [[ "$fail" -gt 0 ]]; then exit 1; fi
exit 0
