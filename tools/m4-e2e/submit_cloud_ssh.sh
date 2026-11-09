#!/bin/bash
# M4 云端成片：scp scene+chess+脚本 → 远端 source env → 127.0.0.1:8787 提交/poll → scp 回 render.png。token 不落地本机。
# 环境：REMOTE(默认 ubuntu@43.192.32.90) VIEW(默认第一个 VIEWS)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
REMOTE="${REMOTE:-ubuntu@43.192.32.90}"
GLB="${GLB:-$ROOT/examples/assets/chess.glb}"; GLB_KEY="${GLB_KEY:-m4/import.glb}"
VIEW="${VIEW:-298cfe60-923d-44fb-a0d1-f2206b9a48e1}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
scp -q -o BatchMode=yes "$HERE/out/m4-scene.json" "$GLB" "$HERE/remote_submit.py" "$REMOTE:/tmp/" 
JOB=$($SSH "$REMOTE" "set -a; . /home/ubuntu/mutracer-cloud/env; set +a; python3 /tmp/remote_submit.py /tmp/m4-scene.json /tmp/$(basename "$GLB") '$GLB_KEY' '$VIEW' /tmp/m4-cloud.png")
scp -q -o BatchMode=yes "$REMOTE:/tmp/m4-cloud.png" "$HERE/out/m4-cloud.png"
cp "$HERE/out/m4-cloud.png" "$HERE/out/m4-cloud-${JOB:0:8}.png"
echo "cloud_job=$JOB png=$HERE/out/m4-cloud.png"
