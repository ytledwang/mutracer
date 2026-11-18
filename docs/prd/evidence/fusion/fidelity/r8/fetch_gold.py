#!/usr/bin/env python3
"""Explicit GET of render_results gold PNGs. Loads .env.production anon key in
memory only; never prints/logs/writes it. Host is http://10.160.9.143:8000 only.
Does not list the bucket. One documented object key per task+view, plus the
same stem without .png if the first 404s.
"""
from __future__ import annotations
import os, sys, hashlib
from pathlib import Path

os.environ["OFFICIAL_PULL_BASE"] = "http://10.160.9.143:8000"
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tools" / "fusion-checks"))
# parents: r8, fidelity, fusion, evidence, prd, docs, mutracer? let's set clearly
sys.path.insert(0, "/Users/wangjianzheng/Project/git/mutracer/tools/fusion-checks")
from official_pull_lib import Client

HOST_OK = "10.160.9.143:8000"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    dest_dir = Path(sys.argv[1])
    dest_dir.mkdir(parents=True, exist_ok=True)
    # argv after dest: taskId viewId destName ...
    args = sys.argv[2:]
    if len(args) % 3 != 0 or not args:
        print("usage: fetch_gold.py DEST_DIR taskId viewId destName [...]", file=sys.stderr)
        return 2
    client = Client(".env.production")
    if not client.base.startswith("http://10.160.9.143"):
        print(f"FAIL unexpected host {client.host}")
        return 1
    if client.host != "10.160.9.143:8000":
        print(f"FAIL unexpected host {client.host}")
        return 1
    failed = 0
    for i in range(0, len(args), 3):
        task, view, name = args[i], args[i + 1], args[i + 2]
        stem = f"{task}_{view}_base_color"
        keys = [f"{task}/{stem}.png", f"{task}/{stem}"]
        dest = dest_dir / name
        got = None
        used = None
        errors = []
        for key in keys:
            try:
                data = client.get_object("render_results", key)
            except RuntimeError as e:
                msg = str(e)
                # redact anything that looks like a token in an error body
                if "eyJ" in msg:
                    msg = msg.split("eyJ")[0] + "[redacted]"
                errors.append(msg[:240])
                continue
            if not data.startswith(b"\x89PNG") and not data[:2] == b"\xff\xd8":
                errors.append(f"{key} not an image header (bytes={len(data)})")
                continue
            got, used = data, key
            break
        if got is None:
            print(f"FAIL {name} tried={keys} errors={errors}")
            failed += 1
            continue
        dest.write_bytes(got)
        print(f"OK {name} key={used} bytes={len(got)} sha256={sha256(got)} dest={dest}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
