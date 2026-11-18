#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-ubuntu@43.192.32.90}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/mutracer-cloud}"
RENDER_BIN="${RENDER_BIN:-/home/ubuntu/mutracer/bin/mutracer-render}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ssh "$REMOTE_HOST" "sudo mkdir -p '$REMOTE_DIR/data' '$REMOTE_DIR/artifacts' && sudo chown -R ubuntu:ubuntu '$REMOTE_DIR'"

scp "$SCRIPT_DIR/api.py" "$SCRIPT_DIR/worker.py" "$REMOTE_HOST:$REMOTE_DIR/"
scp "$SCRIPT_DIR/systemd/mutracer-cloud-api.service" "$SCRIPT_DIR/systemd/mutracer-cloud-worker.service" "$REMOTE_HOST:/tmp/"

ssh "$REMOTE_HOST" bash -s "$REMOTE_DIR" "$RENDER_BIN" <<'REMOTE'
set -euo pipefail
remote_dir="$1"
render_bin="$2"
cd "$remote_dir"

if [[ ! -f env ]]; then
  token="$(openssl rand -hex 32)"
  {
    echo "MUTRACER_API_TOKEN=$token"
    echo "MUTRACER_CLOUD_DB=$remote_dir/data/queue.sqlite3"
    echo "MUTRACER_CLOUD_ARTIFACTS=$remote_dir/artifacts"
    echo "MUTRACER_RENDER_BIN=$render_bin"
    echo "MUTRACER_API_BIND=0.0.0.0"
    echo "MUTRACER_API_PORT=8787"
  } > env
  chmod 600 env
fi

sudo mv /tmp/mutracer-cloud-api.service /etc/systemd/system/mutracer-cloud-api.service
sudo mv /tmp/mutracer-cloud-worker.service /etc/systemd/system/mutracer-cloud-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now mutracer-cloud-api.service mutracer-cloud-worker.service
sudo systemctl restart mutracer-cloud-api.service mutracer-cloud-worker.service
REMOTE

echo "deployed to $REMOTE_HOST:$REMOTE_DIR"
