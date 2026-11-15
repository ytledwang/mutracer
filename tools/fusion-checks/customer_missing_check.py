#!/usr/bin/env python3
"""Checker for the r3 explicit customer_asset pull (fd26af6d, ~50 product GLBs).

Fails if:
  1. the explicit key list is missing / empty / contains a non-customer_asset key
  2. any referenced customer_asset URL in the Front official merge scene is absent locally
  3. any downloaded path / manifest source_key is outside the explicit key list
  4. the pull destination contains a customer_asset object that was not in the allowlist
  5. manifest size/sha256 mismatches, or secrets / signed URLs appear in the manifest
Never prints secret values.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R3 = ROOT / "docs/prd/evidence/fusion/fidelity/r3"
KEYLIST = R3 / "missing-customer-keys.json"
MANIFEST = R3 / "customer-missing-manifest.json"
DEST = ROOT / "tools/cloud-service/poc-out/customer-missing/fd26af6d-43e2-4fa5-8e7e-227d10a3e03f"
SCENE = ROOT / "docs/prd/evidence/fusion/fidelity/r2/scene-official.json"
# Asset map used for the Front official merge (r2), plus r3 overlay if present.
ASSET_MAPS = [
    ROOT / "docs/prd/evidence/fusion/fidelity/r2/official-assets.json",
    R3 / "official-assets.json",
]
STAGE_HK = Path(os.environ.get("MY_STAGE_HK", "/Users/wangjianzheng/Project/HG/my-stage-hk"))
M2_ID = "c83a2f4a-0a3d-4494-8da9-37e6ca6943a7"
ALLOW_PREFIX = "customer_asset/fd26af6d-43e2-4fa5-8e7e-227d10a3e03f/"

fail = 0


def record(ok: bool, name: str, extra: str = "") -> None:
    global fail
    if not ok:
        fail += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}"[:700])


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def secret_values() -> list[str]:
    vals = []
    for name in (".env.production", ".env.local", ".env.development.local", ".env.test"):
        f = STAGE_HK / name
        if not f.is_file():
            continue
        for line in f.read_text(errors="ignore").splitlines():
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
            if not m:
                continue
            k, v = m[1], m[2].strip().strip("\"'")
            if re.search(r"KEY|SECRET|TOKEN|PASSWORD|JWT", k, re.I) and len(v) >= 16:
                vals.append(v)
    return sorted(set(vals))


def load_asset_map() -> dict[str, str]:
    amap: dict[str, str] = {}
    for p in ASSET_MAPS:
        if p.is_file():
            amap.update(json.loads(p.read_text()))
    return amap


def referenced_customer_keys(scene: dict) -> set[str]:
    keys = set()
    meshes = scene.get("meshes") or {}
    for m in (scene.get("models") or {}).values():
        if m.get("type") != "model" or not m.get("mesh"):
            continue
        url = (meshes.get(m["mesh"]) or {}).get("url")
        if isinstance(url, str) and url.startswith("customer_asset/"):
            keys.add(url)
    # also any customer_asset texture urls in the merge
    for t in (scene.get("textures") or {}).values():
        url = t.get("urls") or t.get("url")
        if isinstance(url, str) and url.startswith("customer_asset/"):
            keys.add(url)
    return keys


def main() -> int:
    if not KEYLIST.is_file():
        record(False, "explicit key list exists", str(KEYLIST))
        return 1
    listing = json.loads(KEYLIST.read_text())
    allow = list(listing.get("keys") or [])
    record(len(allow) > 0, "explicit key list non-empty", f"n={len(allow)}")
    bad_keys = [k for k in allow if not k.startswith(ALLOW_PREFIX) or k.endswith("/") or ".." in k]
    record(not bad_keys, "every explicit key is under fd26af6d models/", f"bad={bad_keys[:3]}")
    allow_set = set(allow)

    if not SCENE.is_file():
        record(False, "Front official merge scene exists", str(SCENE))
        return 1
    scene = json.loads(SCENE.read_text())
    refs = referenced_customer_keys(scene)
    record(len(refs) > 0, "merge scene has customer_asset references", f"n={len(refs)}")
    missing_from_list = sorted(k for k in refs if k not in allow_set and not Path(load_asset_map().get(k, "")).is_file())
    # The 50 were the ones not on disk at r2 time. Other customer_asset refs must already be local.
    amap = load_asset_map()

    if not MANIFEST.is_file():
        record(False, "manifest exists", str(MANIFEST))
        # still report referenced misses against current maps
        missing_now = [k for k in refs if not Path(amap.get(k, "")).is_file()]
        record(not missing_now, "every referenced customer_asset is present locally", f"missing={len(missing_now)} first={missing_now[:3]}")
        return 1
    record(True, "manifest exists", str(MANIFEST.relative_to(ROOT)))
    man = json.loads(MANIFEST.read_text())
    files = man.get("files") or []
    record(len(files) > 0, "manifest.files non-empty", f"count={len(files)}")

    blob = json.dumps(man)
    record(not re.search(r"token=|X-Amz-|sign/|Signature=|eyJ[A-Za-z0-9_-]{10,}", blob),
           "no signed URL / token in manifest")
    record(M2_ID not in blob, "M2 replace_id absent from manifest")

    outside = []
    mismatch = []
    seen = set()
    for it in files:
        key = it.get("source_key") or ""
        seen.add(key)
        if key not in allow_set:
            outside.append(key)
            continue
        dest = DEST / Path(key).relative_to("customer_asset/fd26af6d-43e2-4fa5-8e7e-227d10a3e03f")
        # allow explicit path field
        p = ROOT / it["path"] if not Path(it.get("path") or "").is_absolute() else Path(it["path"])
        if not p.is_file():
            p = dest
        if not p.is_file():
            mismatch.append(f"missing {key}")
            continue
        if p.stat().st_size != it.get("size") or sha256_file(p) != it.get("sha256"):
            mismatch.append(f"hash/size {key}")
    record(not outside, "no manifest source_key outside explicit list", f"n={len(outside)} {outside[:3]}")
    record(not mismatch, "manifest files exist with matching size+sha256", f"bad={mismatch[:3]}")
    missing_allow = sorted(allow_set - seen)
    record(not missing_allow, "every explicit key is in the manifest", f"n={len(missing_allow)} {missing_allow[:3]}")

    # Pull destination must only contain allowlisted objects (plus manifest if any).
    extra = []
    if DEST.is_dir():
        for p in DEST.rglob("*"):
            if not p.is_file():
                continue
            if p.name in {"manifest.json", ".DS_Store"}:
                continue
            rel = p.relative_to(DEST).as_posix()
            key = f"customer_asset/fd26af6d-43e2-4fa5-8e7e-227d10a3e03f/{rel}"
            if key not in allow_set:
                extra.append(key)
    record(not extra, "pull dest has no customer_asset object outside the allowlist", f"n={len(extra)} {extra[:3]}")

    # Refresh map with pulled files and require every merge customer_asset ref to exist.
    if DEST.is_dir():
        for it in files:
            key = it.get("source_key")
            p = ROOT / it["path"] if it.get("path") and not Path(it["path"]).is_absolute() else Path(it.get("path") or "")
            if key and p.is_file():
                amap[key] = str(p)
            else:
                dest = DEST / Path(key).relative_to("customer_asset/fd26af6d-43e2-4fa5-8e7e-227d10a3e03f")
                if dest.is_file():
                    amap[key] = str(dest)
    missing_now = [k for k in refs if not Path(amap.get(k, "")).is_file()]
    record(not missing_now, "every referenced customer_asset in the Front official merge is present",
           f"missing={len(missing_now)} first={missing_now[:3]}")

    # Secret scan (values never printed)
    secrets = secret_values()
    record(len(secrets) > 0, "secret values loaded for scan (not printed)", f"n={len(secrets)}")
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        os.chmod(tf.name, 0o600)
        tf.write("\n".join(secrets) + "\n")
        pat = tf.name
    try:
        r = subprocess.run(
            ["grep", "-rlF", "--exclude-dir=node_modules", "--exclude-dir=.git", "-f", pat, str(ROOT), str(DEST.parent if DEST.parent.exists() else DEST)],
            capture_output=True, text=True,
        )
        hits = [h for h in r.stdout.split("\n") if h]
        record(not hits, "secret values absent from repo and pull dest", f"files={hits[:5]}")
    finally:
        os.unlink(pat)

    return 1 if fail else 0


if __name__ == "__main__":
    rc = main()
    print(f"SUMMARY  fail={fail}")
    sys.exit(rc)
