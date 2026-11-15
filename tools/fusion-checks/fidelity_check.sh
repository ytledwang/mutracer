#!/usr/bin/env bash
# Fidelity comparison acceptance check (written before rendering).
# Verifies each render PNG exists, is 1920x1080, is non-blank, has a matching
# .sha256 and a non-empty render .log, and that the comparison image exists.
# Exit 0 only if every item passes. Never git add / commit / push.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python3 "$ROOT/tools/fusion-checks/fidelity_check.py" "$@"
