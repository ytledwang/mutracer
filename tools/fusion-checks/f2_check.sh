#!/usr/bin/env bash
# F2 acceptance entry. Records every item even if one fails. Exit 1 if any fail.
# Never git add / commit / push. Never overwrite docs/prd/evidence/fusion/f2/* r1 files.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
EV="$ROOT/docs/prd/evidence/fusion/f2/r2"
mkdir -p "$EV"
REPORT="$EV/f2-check-report.json"
LOG="$EV/f2-check.sh.log"
: > "$LOG"

pass=0
fail=0
declare -a ITEMS=()

record() {
  local name="$1" code="$2" cmd="$3" extra="${4:-}"
  if [[ "$code" -eq 0 ]]; then
    ITEMS+=("PASS|$name|$code|$cmd|$extra")
    pass=$((pass + 1))
    echo "PASS  $name  exit=$code" | tee -a "$LOG"
  else
    ITEMS+=("FAIL|$name|$code|$cmd|$extra")
    fail=$((fail + 1))
    echo "FAIL  $name  exit=$code" | tee -a "$LOG"
  fi
}

run_item() {
  local name="$1"; shift
  local cmd="$*"
  echo "+ $cmd" | tee -a "$LOG"
  set +e
  eval "$cmd" >>"$LOG" 2>&1
  local code=$?
  set -u
  record "$name" "$code" "$cmd"
}

run_item "typecheck:viewer" "npm run typecheck:viewer"
run_item "test:viewer" "npm run test:viewer"
run_item "scene-template smoke" "node tools/scene-template/smoke.mjs"

# Live UI checks (headed Chrome). f2_check.mjs writes its own per-item report.
set +e
NODE_PATH="/tmp/mutracer-f2/node_modules${NODE_PATH:+:$NODE_PATH}" \
  node tools/fusion-checks/f2_check.mjs --evidence "$EV" >>"$LOG" 2>&1
ui_code=$?
set -u
record "f2_check.mjs (headed UI)" "$ui_code" "node tools/fusion-checks/f2_check.mjs --evidence $EV" "$EV/f2-ui-report.json"

# Summarize
{
  echo "{"
  echo "  \"pass\": $pass,"
  echo "  \"fail\": $fail,"
  echo "  \"items\": ["
  first=1
  for row in "${ITEMS[@]}"; do
    IFS='|' read -r status name code cmd extra <<<"$row"
    if [[ $first -eq 0 ]]; then echo ","; fi
    first=0
    python3 - "$status" "$name" "$code" "$cmd" "$extra" <<'PY'
import json,sys
status,name,code,cmd,extra=sys.argv[1:]
print("    "+json.dumps({"status":status,"name":name,"exit":int(code),"command":cmd,"extra":extra},ensure_ascii=False), end="")
PY
  done
  echo
  echo "  ]"
  echo "}"
} > "$REPORT"

echo
echo "F2 check summary: pass=$pass fail=$fail  report=$REPORT"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
