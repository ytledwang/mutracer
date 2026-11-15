#!/usr/bin/env python3
"""Read-only pull of official RF_Kitchen_0302_Scene + gold-sample official
materials/environments from http://10.160.9.143:8000 (Render2-supabase).
Uses my-stage-hk .env.production anon key in memory only. Never prints secrets.
Never touches customer_asset. Never lists the bucket. Explicit keys only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OFFICIAL_PULL_BASE", "http://10.160.9.143:8000")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_pull_lib import Client  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tools/cloud-service/poc-out/official/ccdaa114"
OFFICIAL_ID = "ccdaa114-cdb7-4ef5-af26-022938a780d5"
LOG = Path.home() / "mutracer-scratch/official_pull/pull.log"
HDRI_MIN = 100 * 1024

# Official materials / environments referenced by the local 1.0 gold fridge sample
# (product scene.json + merged template). Explicit keys only — not the whole library.
GOLD_KEYS = [
    "official_asset/material/ede95c7f-fb5d-44d6-abad-cb9458616a90/textures/T_MetalWear_Frosted_R.exr",
    "official_asset/material/ede95c7f-fb5d-44d6-abad-cb9458616a90/textures/T_MetalWear_Frosted_N.exr",
    "official_asset/material/ea684aef-b2c2-4b12-b264-27449c21c5ed/textures/T_MetalWear_Frosted_R.exr",
    "official_asset/material/ea684aef-b2c2-4b12-b264-27449c21c5ed/textures/T_MetalWear_Frosted_N.exr",
    "official_asset/material/f7b081d4-c512-4f09-9452-bb130deafd74/textures/T_Mask_03.png",
    "official_asset/good_templates/Empty_file/textures/GradientTexture0.tga",
    "official_asset/environment/8c2e21fc-bc21-4904-80a7-990eb69c9ff3/textures/25.exr",
    "official_asset/environment/8ffebd47-fb14-4175-bcac-dd9a175b7bde/textures/4.exr",
    "official_asset/environment/8115f2b2-a7bf-4b11-9ef3-5f602f804869/textures/3.exr",
    "official_asset/environment/0d718b1b-976d-4225-8ce6-ae514f45eea9/textures/16.exr",
    "official_asset/environment/76d03ac0-9721-4170-84a2-f461a78f9bf5/textures/brown_photostudio_02_2k.exr",
]
WHITE_KEY = "official_asset/template/RF_Scene_Kitchen_2cam/textures/White.exr"
SHELL_SCENE_KEY = "official_asset/template/RF_Kitchen_0302_Scene/scene.json"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S %z')}  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def split_key(key: str) -> tuple[str, str]:
    if not key.startswith("official_asset/"):
        raise RuntimeError(f"refusing non-official key: {key[:80]}")
    if "customer_asset" in key:
        raise RuntimeError("refusing customer_asset")
    return "official_asset", key[len("official_asset/"):]


def collect_official_keys(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("url", "urls") and isinstance(v, str) and v.startswith("official_asset/"):
                out.add(v)
            else:
                collect_official_keys(v, out)
    elif isinstance(obj, list):
        for x in obj:
            collect_official_keys(x, out)


def main() -> int:
    FIX.mkdir(parents=True, exist_ok=True)
    client = Client(".env.production")
    if not client.base.startswith("http://10.160.9.143"):
        log(f"FAIL unexpected base host={client.host}")
        return 1
    log(f"pull start host={client.host} dest={FIX}")

    # 1) official shell scene.json
    scene_bytes = client.get_object(*split_key(SHELL_SCENE_KEY))
    scene = json.loads(scene_bytes)
    shell_dir = FIX / "shell"
    shell_dir.mkdir(parents=True, exist_ok=True)
    (shell_dir / "scene.json").write_bytes(scene_bytes)
    log(f"shell scene.json bytes={len(scene_bytes)}")
    if OFFICIAL_ID not in json.dumps(scene):
        log("FAIL official replace_id missing from scene.json")
        return 1

    shell_keys: set[str] = set()
    collect_official_keys(scene, shell_keys)
    log(f"shell referenced official keys={len(shell_keys)}")

    # 2) White.exr size check (known explicit library path from the M2 backup template)
    white_meta = {
        "name": "White.exr",
        "source_key": WHITE_KEY,
        "used": False,
        "placeholder_not_used": False,
        "size": 0,
    }
    try:
        white = client.get_object(*split_key(WHITE_KEY))
        white_meta["size"] = len(white)
        if len(white) <= HDRI_MIN:
            white_meta["placeholder_not_used"] = True
            white_meta["used"] = False
            log(f"White.exr is placeholder size={len(white)} — will not use as environment")
        else:
            log(f"White.exr looks real size={len(white)}")
        rel = Path(WHITE_KEY)
        dest = FIX / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(white)
        white_meta["path"] = str(rel)
        white_meta["sha256"] = sha256_bytes(white)
    except RuntimeError as e:
        log(f"White.exr GET failed: {e}")
        white_meta["error"] = str(e)[:200]
        white = None

    # 3) Download every referenced shell asset + gold official materials/envs + White.exr
    wanted = []
    seen = set()
    def add(key: str, role: str) -> None:
        if key in seen:
            return
        seen.add(key)
        wanted.append((key, role))

    add(SHELL_SCENE_KEY, "shell_scene")
    for k in sorted(shell_keys):
        add(k, "shell")
    add(WHITE_KEY, "hdri_placeholder_check")
    for k in GOLD_KEYS:
        add(k, "gold_official")

    files = []
    missing = []
    env_entries = []
    if white is not None:
        env_entries.append({
            "name": "White.exr",
            "source_key": WHITE_KEY,
            "size": white_meta["size"],
            "used": False,
            "placeholder_not_used": white_meta["placeholder_not_used"],
        })

    for i, (key, role) in enumerate(wanted, 1):
        rel = Path(key)
        dest = FIX / rel
        # shell scene also stored under shell/scene.json (canonical checker path)
        try:
            if dest.is_file() and role != "shell_scene":
                data = dest.read_bytes()
                log(f"[{i}/{len(wanted)}] reuse {key} bytes={len(data)}")
            else:
                data = client.get_object(*split_key(key))
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                log(f"[{i}/{len(wanted)}] got {key} bytes={len(data)} role={role}")
        except RuntimeError as e:
            log(f"[{i}/{len(wanted)}] FAIL {key} {e}")
            missing.append({"source_key": key, "role": role, "error": str(e)[:200]})
            continue
        rec = {
            "path": str(rel).replace("\\", "/"),
            "size": len(data),
            "sha256": sha256_bytes(data),
            "source_key": key,
            "role": role,
        }
        files.append(rec)
        if role == "shell_scene":
            # duplicate entry for checker path shell/scene.json
            files.append({
                "path": "shell/scene.json",
                "size": len(data),
                "sha256": rec["sha256"],
                "source_key": key,
                "role": "shell_scene_canonical",
            })
        if "/environment/" in key or key.lower().endswith(".exr") and "White.exr" not in key:
            used = key.endswith("16.exr")  # product gold sample's scene environment image
            env_entries.append({
                "name": Path(key).name,
                "source_key": key,
                "size": len(data),
                "used": used,
                "placeholder_not_used": False,
            })

    # Prefer a real HDRI (>100KB). 16.exr is the gold fridge sample's environment.
    real_used = [e for e in env_entries if e.get("used") and (e.get("size") or 0) > HDRI_MIN]
    if not real_used:
        for e in env_entries:
            if not e.get("placeholder_not_used") and (e.get("size") or 0) > HDRI_MIN:
                e["used"] = True
                real_used.append(e)
                break

    all_shell_keys = sorted(shell_keys | {SHELL_SCENE_KEY})
    have = {f["source_key"] for f in files}
    shell_missing = [k for k in all_shell_keys if k not in have]

    manifest = {
        "replace_id": OFFICIAL_ID,
        "template_name": "RF_Kitchen_0302_Scene",
        "template_data_bucket_url": "official_asset/template/RF_Kitchen_0302_Scene",
        "source": {
            "host": client.host,
            "base": "http://10.160.9.143:8000",
            "envfile": ".env.production",
            "note": "Render2-supabase private IP over Mac mini VPN. No signed URLs, no secrets.",
        },
        "files": files,
        "references": {
            "texture_refs": sum(1 for k in shell_keys if "/textures/" in k),
            "mesh_refs": sum(1 for k in shell_keys if "/models/" in k),
            "all_keys": all_shell_keys,
            "missing": shell_missing,
        },
        "environment": env_entries,
        "environment_none_used_reason": None
        if real_used
        else "RF_Kitchen_0302_Scene has no environment (active_environment=0); White.exr is a placeholder; no real HDRI could be fetched.",
        "white_exr": white_meta,
        "pulled_at": time.strftime("%Y-%m-%d %H:%M:%S %z") + " Asia/Shanghai",
    }
    (FIX / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    log(
        f"manifest written files={len(files)} missing={len(missing)+len(shell_missing)} "
        f"total_bytes={sum(f['size'] for f in files)}"
    )
    if missing or shell_missing:
        log(f"FAIL missing keys={missing or shell_missing}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
