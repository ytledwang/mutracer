#!/usr/bin/env python3
import base64
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DB = Path(os.environ["MUTRACER_CLOUD_DB"])
ARTIFACTS = Path(os.environ["MUTRACER_CLOUD_ARTIFACTS"])
TOKEN = os.environ.get("MUTRACER_API_TOKEN", "")
BIND = os.environ.get("MUTRACER_API_BIND", "0.0.0.0")
PORT = int(os.environ.get("MUTRACER_API_PORT", "8787"))


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB, timeout=30)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              scene_path TEXT NOT NULL,
              assets_dir TEXT NOT NULL,
              params TEXT NOT NULL,
              result_path TEXT,
              error TEXT
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, created_at)")
        conn.commit()


def json_response(handler, code, value):
    body = json.dumps(value, ensure_ascii=False).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def png_response(handler, path):
    path = Path(path)
    if not path.is_file():
        json_response(handler, 404, {"error": "result not ready"})
        return
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "image/png")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def authorized(handler):
    if not TOKEN:
        return True
    return handler.headers.get("Authorization") == f"Bearer {TOKEN}"


def write_assets(base_dir, assets):
    assets_dir = base_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for name, encoded in assets.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid asset path")
        dest = assets_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(base64.b64decode(encoded))
        mapping[name] = str(dest)
    (base_dir / "assets.json").write_text(json.dumps(mapping), encoding="utf-8")
    return assets_dir


class Handler(BaseHTTPRequestHandler):
    server_version = "MutracerCloudAPI/1.0"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if not authorized(self):
            json_response(self, 401, {"error": "unauthorized"})
            return
        path = urlsplit(self.path).path
        if path == "/healthz":
            json_response(self, 200, {"status": "ok", "time": now()})
            return
        if path.startswith("/v1/jobs/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                job_id = parts[2]
                with closing(sqlite3.connect(DB, timeout=30)) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None:
                    json_response(self, 404, {"error": "job not found"})
                else:
                    json_response(self, 200, dict(row))
                return
            if len(parts) == 4 and parts[3] == "render.png":
                job_id = parts[2]
                with closing(sqlite3.connect(DB, timeout=30)) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT result_path FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None or not row["result_path"]:
                    json_response(self, 404, {"error": "job not found"})
                else:
                    png_response(self, row["result_path"])
                return
        json_response(self, 404, {"error": "not found"})

    def do_POST(self):
        if not authorized(self):
            json_response(self, 401, {"error": "unauthorized"})
            return
        if urlsplit(self.path).path != "/v1/jobs":
            json_response(self, 404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload.get("scene"), dict):
                raise ValueError("scene must be an object")
            if payload.get("kind", "render") != "render":
                raise ValueError("only render jobs are supported")
            if not isinstance(payload.get("assets", {}), dict):
                raise ValueError("assets must be an object")
            if not isinstance(payload.get("params", {}), dict):
                raise ValueError("params must be an object")
            job_id = uuid.uuid4().hex
            base_dir = ARTIFACTS / job_id
            base_dir.mkdir(parents=True, exist_ok=True)
            scene_path = base_dir / "scene.json"
            scene_path.write_text(json.dumps(payload["scene"], ensure_ascii=False), encoding="utf-8")
            assets_dir = write_assets(base_dir, payload.get("assets", {}))
            params = payload.get("params", {})
            with closing(sqlite3.connect(DB, timeout=30)) as conn:
                conn.execute(
                    """INSERT INTO jobs
                       (id, kind, status, created_at, updated_at, scene_path, assets_dir, params)
                       VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)""",
                    (job_id, "render", now(), now(), str(scene_path), str(assets_dir), json.dumps(params)),
                )
                conn.commit()
            json_response(self, 201, {"id": job_id, "status": "queued"})
        except Exception as error:
            json_response(self, 400, {"error": str(error)})


if __name__ == "__main__":
    init_db()
    print(f"MuTracer cloud API listening on {BIND}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
