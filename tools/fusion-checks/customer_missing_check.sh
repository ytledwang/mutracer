#!/usr/bin/env bash
# Acceptance check for the explicit missing customer_asset GLB pull (r3).
# Written before pulling. Exit 0 only if every item passes. Never git add / commit.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python3 "$ROOT/tools/fusion-checks/customer_missing_check.py" "$@"
