#!/usr/bin/env bash
# Official 可影 content pull acceptance check (written before pulling).
# Exit 0 only if every item passes. Never git add / commit / push.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python3 "$ROOT/tools/fusion-checks/official_pull_check.py" "$@"
