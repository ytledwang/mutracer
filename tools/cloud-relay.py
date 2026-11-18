#!/usr/bin/env python3
"""Minimal SQLite-backed relay for the cloud MuTracer render POC."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("poc/cloud-relay.sqlite3")
DEFAULT_TASK_DIR = Path("poc/tasks")
DEFAULT_HOST = "ubuntu@43.192.32.90"
DEFAULT_BIN = "/home/ubuntu/mutracer/bin/mutracer-render"
DEFAULT_PIPELINE = "/home/ubuntu/stage-stack/converter/pipelines/blender_pipeline/2json.py"



REPO_ROOT = Path(__file__).resolve().parent.parent
IMPORT_CONTRACT = REPO_ROOT / "tools" / "import-contract"
EXPORT_PRESET = IMPORT_CONTRACT / "export_glb_preset.py"
VALIDATE_GLB = IMPORT_CONTRACT / "validate_glb.py"


def official_export_remote_cmd(remote_script: str, remote_input: str, remote_glb: str, importer: str) -> str:
    """Build the remote Blender command that uses the official export preset."""
    return (
        f"blender --background --python {shlex.quote(remote_script)} -- "
        f"--input {shlex.quote(remote_input)} --output {shlex.quote(remote_glb)} --importer {importer}"
    )


def validate_remote_cmd(remote_validator: str, remote_glb: str, *, source_units: str | None = None) -> str:
    cmd = f"python3 {shlex.quote(remote_validator)} {shlex.quote(remote_glb)}"
    if source_units == "mm":
        cmd += " --source-units mm --unit-scale 1"
    return cmd


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS render_jobs (
          id TEXT PRIMARY KEY,
          scene_path TEXT NOT NULL,
          asset_map_path TEXT NOT NULL,
          status TEXT NOT NULL,
          remote_host TEXT NOT NULL,
          remote_bin TEXT NOT NULL,
          view TEXT,
          width INTEGER NOT NULL,
          height INTEGER NOT NULL,
          samples INTEGER NOT NULL,
          bounces INTEGER NOT NULL,
          denoise INTEGER NOT NULL,
          output_path TEXT,
          error TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conversion_jobs (
          id TEXT PRIMARY KEY,
          input_path TEXT NOT NULL,
          status TEXT NOT NULL,
          remote_host TEXT NOT NULL,
          pipeline_script TEXT NOT NULL,
          output_path TEXT,
          scene_path TEXT,
          preview_path TEXT,
          asset_map_path TEXT,
          error TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT
        );
        """
    )
    return connection


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=check, text=True, capture_output=True)


def add_job(args: argparse.Namespace) -> None:
    connection = connect(args.database)
    scene_path = Path(args.scene).resolve()
    asset_map_path = Path(args.asset_map).resolve()
    if not scene_path.is_file() or not asset_map_path.is_file():
        raise SystemExit("scene and asset map must exist")
    job_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO render_jobs VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL)",
        (
            job_id,
            str(scene_path),
            str(asset_map_path),
            args.host,
            args.bin,
            args.view,
            args.width,
            args.height,
            args.samples,
            args.bounces,
            int(args.denoise),
            now(),
        ),
    )
    connection.commit()
    print(job_id)


def local_assets(asset_map_path: Path) -> dict[str, Path]:
    values: dict[str, str] = json.loads(asset_map_path.read_text())
    return {url: Path(path).resolve() for url, path in values.items()}


def add_conversion(args: argparse.Namespace) -> None:
    connection = connect(args.database)
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise SystemExit("input file must exist")
    job_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO conversion_jobs VALUES (?, ?, 'pending', ?, ?, NULL, NULL, NULL, NULL, NULL, ?, NULL, NULL)",
        (
            job_id,
            str(input_path),
            args.host,
            args.pipeline_script,
            now(),
        ),
    )
    connection.commit()
    print(job_id)


def remote(host: str, script: str) -> subprocess.CompletedProcess[str]:
    return run(["ssh", host, script])


def run_conversion(args: argparse.Namespace) -> None:
    job_id = args.id
    connection = connect(args.database)
    job = connection.execute("SELECT * FROM conversion_jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise SystemExit("conversion job not found")
    if job["status"] == "running":
        raise SystemExit("conversion job is already running")

    task_dir = args.task_dir / job_id
    remote_dir = f"/tmp/mutracer-relay-{job_id}"
    input_path = Path(job["input_path"])
    output_path = task_dir / "output"
    scene_path = output_path / "scene.json"
    preview_path = output_path / "preview.png"
    asset_map_path = task_dir / "assets.json"
    task_dir.mkdir(parents=True, exist_ok=True)
    connection.execute("UPDATE conversion_jobs SET status = 'running', started_at = ?, error = NULL WHERE id = ?", (now(), job_id))
    connection.commit()

    try:
        shutil.rmtree(output_path, ignore_errors=True)
        remote(job["remote_host"], f"rm -rf {shlex.quote(remote_dir)} && mkdir -p {shlex.quote(remote_dir)}/input {shlex.quote(remote_dir)}/output/models")
        run(["scp", str(input_path), f"{job['remote_host']}:{remote_dir}/input/{input_path.name}"])

        remote_input = f"{remote_dir}/input/{input_path.name}"
        remote_stl = f"{remote_dir}/model.stl"
        remote_glb = f"{remote_dir}/model.glb"
        extension = input_path.suffix.lower()
        remote_preset = f"{remote_dir}/export_glb_preset.py"
        remote_validator = f"{remote_dir}/validate_glb.py"
        if not EXPORT_PRESET.is_file() or not VALIDATE_GLB.is_file():
            raise SystemExit(f"import-contract scripts missing: {EXPORT_PRESET} / {VALIDATE_GLB}")
        run(["scp", str(EXPORT_PRESET), str(VALIDATE_GLB), f"{job['remote_host']}:{remote_dir}/"])

        source_units = None
        if extension in {".step", ".stp"}:
            remote(job["remote_host"], f"gmsh -3 {shlex.quote(remote_input)} -format stl -o {shlex.quote(remote_stl)} -v 3")
            remote(job["remote_host"], official_export_remote_cmd(remote_preset, remote_stl, remote_glb, "stl"))
            source_units = "mm"
        elif extension == ".stl":
            remote(job["remote_host"], official_export_remote_cmd(remote_preset, remote_input, remote_glb, "stl"))
            source_units = "mm"
        elif extension in {".glb", ".gltf"}:
            remote_glb = remote_input
        else:
            raise SystemExit("supported conversion inputs: .step, .stp, .stl, .glb, .gltf")

        validate_cmd = validate_remote_cmd(remote_validator, remote_glb, source_units=source_units)
        validate = run(["ssh", job["remote_host"], validate_cmd], check=False)
        if validate.returncode != 0:
            log = ((validate.stdout or "") + (validate.stderr or "")).strip()
            if getattr(args, "allow_contract_failures", False):
                print("import-contract failed but --allow-contract-failures is set; continuing:\n" + log, flush=True)
            else:
                raise SystemExit(f"import-contract validation failed for {remote_glb}:\n{log}")

        remote(job["remote_host"], f"cp {shlex.quote(remote_glb)} {shlex.quote(remote_dir)}/input/model.glb")
        remote(
            job["remote_host"],
            f"cd {shlex.quote(remote_dir)} && touch output/conversion_log.txt && printf '%s\\n' '{{}}' > output/status.json && blender --background --python {shlex.quote(job['pipeline_script'])}",
        )
        run(["scp", "-r", f"{job['remote_host']}:{remote_dir}/output", str(output_path.parent)])
        if not scene_path.is_file():
            raise FileNotFoundError("remote conversion did not produce scene.json")

        model_paths = sorted((output_path / "models").glob("*.glb"))
        if not model_paths:
            raise FileNotFoundError("remote conversion did not produce a model GLB")
        asset_url = f"models/{model_paths[0].name}"
        asset_map_path.write_text(json.dumps({asset_url: str(model_paths[0].resolve())}))
        connection.execute(
            "UPDATE conversion_jobs SET status = 'succeed', output_path = ?, scene_path = ?, preview_path = ?, asset_map_path = ?, finished_at = ? WHERE id = ?",
            (
                str(output_path.resolve()),
                str(scene_path.resolve()),
                str(preview_path.resolve()) if preview_path.is_file() else None,
                str(asset_map_path.resolve()),
                now(),
                job_id,
            ),
        )
        print(json.dumps(dict(connection.execute("SELECT * FROM conversion_jobs WHERE id = ?", (job_id,)).fetchone()), indent=2))
    except subprocess.CalledProcessError as error:
        message = (error.stderr or error.stdout or str(error)).strip()
        connection.execute(
            "UPDATE conversion_jobs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
            (message, now(), job_id),
        )
        raise SystemExit(message) from error
    finally:
        connection.commit()


def render_job(args: argparse.Namespace) -> None:
    job_id = args.id
    connection = connect(args.database)
    job = connection.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise SystemExit("job not found")
    if job["status"] == "running":
        raise SystemExit("job is already running")

    task_dir = args.task_dir / job_id
    remote_dir = f"/tmp/mutracer-relay-{job_id}"
    scene_path = task_dir / "scene.json"
    asset_map_path = task_dir / "assets.json"
    output_path = task_dir / "render.png"
    task_dir.mkdir(parents=True, exist_ok=True)
    connection.execute("UPDATE render_jobs SET status = 'running', started_at = ?, error = NULL WHERE id = ?", (now(), job_id))
    connection.commit()

    try:
        shutil.copyfile(job["scene_path"], scene_path)
        assets = local_assets(Path(job["asset_map_path"]))
        for local_path in assets.values():
            if not local_path.is_file():
                raise FileNotFoundError(local_path)

        run(["ssh", job["remote_host"], f"rm -rf {remote_dir} && mkdir -p {remote_dir}"])
        run(["scp", str(scene_path), f"{job['remote_host']}:{remote_dir}/scene.json"])
        for url, local_path in assets.items():
            remote_path = f"{remote_dir}/{url.rsplit('/', 1)[-1]}"
            run(["scp", str(local_path), f"{job['remote_host']}:{remote_path}"])
        remote_assets = {
            url: f"{remote_dir}/{path.name}" for url, path in assets.items()
        }
        asset_map_path.write_text(json.dumps(remote_assets))
        run(["scp", str(asset_map_path), f"{job['remote_host']}:{remote_dir}/assets.json"])

        command = [
            job["remote_bin"],
            "--scene", f"{remote_dir}/scene.json",
            "--out", f"{remote_dir}/render.png",
            "--asset-map", f"{remote_dir}/assets.json",
            "--camera-target", "0,0,0",
            "--width", str(job["width"]),
            "--height", str(job["height"]),
            "--samples", str(job["samples"]),
            "--bounces", str(job["bounces"]),
            "--denoise", "1" if job["denoise"] else "0",
            "--light-scale", "1",
            "--timeout-ms", str(args.timeout_ms),
        ]
        if job["view"]:
            command.extend(["--view", job["view"]])
        run(["ssh", job["remote_host"], " ".join(command)])
        run(["scp", f"{job['remote_host']}:{remote_dir}/render.png", str(output_path)])

        connection.execute(
            "UPDATE render_jobs SET status = 'succeed', output_path = ?, finished_at = ? WHERE id = ?",
            (str(output_path.resolve()), now(), job_id),
        )
        print(output_path.resolve())
    except subprocess.CalledProcessError as error:
        message = (error.stderr or error.stdout or str(error)).strip()
        connection.execute(
            "UPDATE render_jobs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
            (message, now(), job_id),
        )
        raise SystemExit(message) from error
    finally:
        connection.commit()


def show_job(args: argparse.Namespace) -> None:
    connection = connect(args.database)
    job = connection.execute("SELECT * FROM render_jobs WHERE id = ?", (args.id,)).fetchone()
    if not job:
        raise SystemExit("job not found")
    print(json.dumps(dict(job), indent=2))


def list_jobs(args: argparse.Namespace) -> None:
    connection = connect(args.database)
    rows = connection.execute("SELECT id, status, output_path, error, created_at FROM render_jobs").fetchall()
    for row in rows:
        print(json.dumps(dict(row), ensure_ascii=False))


def list_conversions(args: argparse.Namespace) -> None:
    connection = connect(args.database)
    rows = connection.execute("SELECT id, status, scene_path, preview_path, error, created_at FROM conversion_jobs").fetchall()
    for row in rows:
        print(json.dumps(dict(row), ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--database", type=Path, default=DEFAULT_DB)
    result.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    commands = result.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add")
    add.add_argument("--scene", type=Path, required=True)
    add.add_argument("--asset-map", type=Path, required=True)
    add.add_argument("--host", default=DEFAULT_HOST)
    add.add_argument("--bin", default=DEFAULT_BIN)
    add.add_argument("--view")
    add.add_argument("--width", type=int, default=1280)
    add.add_argument("--height", type=int, default=720)
    add.add_argument("--samples", type=int, default=16)
    add.add_argument("--bounces", type=int, default=3)
    add.add_argument("--denoise", action="store_true")
    add.set_defaults(function=add_job)

    render = commands.add_parser("render")
    render.add_argument("id")
    render.add_argument("--timeout-ms", type=int, default=120000)
    render.set_defaults(function=render_job)

    convert = commands.add_parser("convert")
    convert.add_argument("id")
    convert.add_argument(
        "--allow-contract-failures",
        action="store_true",
        help="Continue the remote pipeline even if import-contract validation fails",
    )
    convert.set_defaults(function=run_conversion)

    conversion_parser = commands.add_parser("add-conversion")
    conversion_parser.add_argument("--input", type=Path, required=True)
    conversion_parser.add_argument("--host", default=DEFAULT_HOST)
    conversion_parser.add_argument("--pipeline-script", default=DEFAULT_PIPELINE)
    conversion_parser.set_defaults(function=add_conversion)

    show = commands.add_parser("show")
    show.add_argument("id")
    show.set_defaults(function=show_job)

    listing = commands.add_parser("list")
    listing.set_defaults(function=list_jobs)

    conversion_listing = commands.add_parser("list-conversions")
    conversion_listing.set_defaults(function=list_conversions)
    return result


def main() -> int:
    arguments: argparse.Namespace = parser().parse_args()
    arguments.function(arguments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
