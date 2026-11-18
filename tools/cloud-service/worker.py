#!/usr/bin/env python3
import json
import os
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB = Path(os.environ["MUTRACER_CLOUD_DB"])
ARTIFACTS = Path(os.environ["MUTRACER_CLOUD_ARTIFACTS"])
RENDER_BIN = Path(os.environ.get("MUTRACER_RENDER_BIN", "/home/ubuntu/mutracer/bin/mutracer-render"))
POLL_INTERVAL = float(os.environ.get("MUTRACER_POLL_INTERVAL", "2"))


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


def claim_job():
    with closing(sqlite3.connect(DB, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE jobs SET status = 'processing', updated_at = ? WHERE id = ? AND status = 'queued'",
            (now(), row["id"]),
        )
        conn.commit()
    return dict(row)


def build_command(job, out_path):
    params = json.loads(job["params"])
    command = [
        str(RENDER_BIN),
        "--scene", job["scene_path"],
        "--out", str(out_path),
        "--asset-map", str(Path(job["assets_dir"]).with_name("assets.json")),
        "--camera-target", str(params.get("camera_target", "0,0,0")),
        "--tone-mapping", str(params.get("tone_mapping", "agx")),
        "--width", str(int(params.get("width", 1280))),
        "--height", str(int(params.get("height", 720))),
        "--samples", str(int(params.get("samples", 32))),
        "--bounces", str(int(params.get("bounces", 4))),
        "--denoise", "1" if params.get("denoise", True) else "0",
        "--light-scale", str(float(params.get("light_scale", 1))),
        "--timeout-ms", str(int(params.get("timeout_ms", 600000))),
    ]
    if params.get("view"):
        command.extend(["--view", str(params["view"])])
    if params.get("camera_mode"):
        command.extend(["--camera-mode", str(params["camera_mode"])])
    if params.get("basis"):
        command.extend(["--basis", str(params["basis"])])
    return command, params


def finish(job_id, status, result_path=None, error=None):
    with closing(sqlite3.connect(DB, timeout=30)) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, result_path = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, result_path, error, now(), job_id),
        )
        conn.commit()


def process(job):
    job_dir = Path(job["scene_path"]).parent
    out_path = job_dir / "render.png"
    log_path = job_dir / "render.log"
    command, params = build_command(job, out_path)
    print(f"processing {job['id']}: {' '.join(command)}", flush=True)
    try:
        with log_path.open("ab") as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        if not out_path.is_file():
            raise RuntimeError("renderer did not create output")
        result_path = str(out_path)
        (job_dir / "effective_params.json").write_text(json.dumps(params, ensure_ascii=False), encoding="utf-8")
        finish(job["id"], "succeed", result_path)
        print(f"succeed {job['id']} -> {result_path}", flush=True)
    except subprocess.CalledProcessError as error:
        tail = log_path.read_bytes()[-4000:].decode(errors="replace") if log_path.exists() else ""
        finish(job["id"], "failed", None, f"exit {error.returncode}: {tail}")
        print(f"failed {job['id']}: exit {error.returncode}", flush=True)
    except Exception as error:
        finish(job["id"], "failed", None, str(error))
        print(f"failed {job['id']}: {error}", flush=True)


def main():
    init_db()
    print(f"MuTracer cloud worker started; renderer={RENDER_BIN}", flush=True)
    while True:
        job = claim_job()
        if job:
            process(job)
        else:
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
