#!/usr/bin/env python3
"""Official kitchen shell pull check (ccdaa114). Invoked by official_pull_check.sh.

Checks:
  1. manifest.json exists under tools/cloud-service/poc-out/official/ccdaa114/
  2. every manifest file exists locally with matching size + sha256
  3. no manifest path / source key contains customer_asset; no signed-URL tokens
  4. shell scene.json parses; replace_id == ccdaa114-cdb7-4ef5-af26-022938a780d5;
     fixture dir is separate from M2 c83a2f4a (and M2 id does not appear in it)
  5. zero referenced-texture / mesh misses for the shell
  6. HDRI: every env texture used is > 100KB, or is listed as
     placeholder_not_used in manifest.environment
  7. the actual secret values from my-stage-hk env files do not appear in the
     repo working tree or logs (grep -F -l; secrets never printed)
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

OFFICIAL_ID = "ccdaa114-cdb7-4ef5-af26-022938a780d5"
M2_ID = "c83a2f4a-0a3d-4494-8da9-37e6ca6943a7"
ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tools/cloud-service/poc-out/official/ccdaa114"
STAGE_HK = Path(os.environ.get("MY_STAGE_HK", "/Users/wangjianzheng/Project/HG/my-stage-hk"))
HDRI_MIN = 100 * 1024

fail = 0


def record(ok: bool, name: str, extra: str = "") -> None:
    global fail
    if not ok:
        fail += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}"[:600])


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
            k, v = m[1], m[2].strip().strip('"\'')
            if re.search(r"KEY|SECRET|TOKEN|PASSWORD|JWT", k, re.I) and len(v) >= 16:
                vals.append(v)
    return sorted(set(vals))


def secret_scan() -> None:
    secrets = secret_values()
    record(len(secrets) > 0, "secret values loaded for scan (not printed)", f"n={len(secrets)}")
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        os.chmod(tf.name, 0o600)
        tf.write("\n".join(secrets) + "\n")
        pat = tf.name
    try:
        targets = [str(ROOT)]
        r = subprocess.run(
            ["grep", "-rlF", "--exclude-dir=node_modules", "--exclude-dir=.git", "-f", pat, *targets],
            capture_output=True, text=True,
        )
        hits = [h for h in r.stdout.split("\n") if h]
        record(not hits, "secret values absent from repo working tree + logs", f"files={hits[:5]}")
        r2 = subprocess.run(["grep", "-rlF", "-f", pat, str(Path.home() / "mutracer-scratch/official_pull")], capture_output=True, text=True)
        hits2 = [h for h in r2.stdout.split("\n") if h]
        record(not hits2, "secret values absent from scratch official_pull logs", f"files={hits2[:5]}")
    finally:
        os.unlink(pat)



def main() -> int:
    man_p = FIX / "manifest.json"
    if not man_p.is_file():
        record(False, "manifest exists", str(man_p))
        return 1
    record(True, "manifest exists", str(man_p.relative_to(ROOT)))
    man = json.loads(man_p.read_text())
    files = man.get("files") or []
    record(len(files) > 0, "manifest.files non-empty", f"count={len(files)}")

    bad = 0
    total = 0
    for it in files:
        p = FIX / it["path"]
        if not p.is_file():
            bad += 1
            print(f"  missing {it['path']}")
            continue
        sz = p.stat().st_size
        total += sz
        if sz != it.get("size") or sha256_file(p) != it.get("sha256"):
            bad += 1
            print(f"  mismatch {it['path']}")
    record(bad == 0, "manifest files exist with matching size+sha256", f"bad={bad} total_bytes={total}")

    blob = json.dumps(man)
    record("customer_asset" not in blob, "no customer_asset in manifest paths/keys")
    record(not re.search(r"token=|X-Amz-|sign/|Signature=|eyJ[A-Za-z0-9_-]{10,}", blob),
           "no signed URL / token in manifest")
    on_disk_ca = [str(p) for p in FIX.rglob("*") if "customer_asset" in str(p.relative_to(FIX))]
    record(not on_disk_ca, "no customer_asset path on disk under fixture", f"n={len(on_disk_ca)}")

    shell = FIX / "shell/scene.json"
    try:
        scene = json.loads(shell.read_text())
        record(True, "shell scene.json parses", str(shell.relative_to(ROOT)))
    except Exception as e:  # noqa: BLE001
        record(False, "shell scene.json parses", repr(e))
        return 1
    rid = man.get("replace_id")
    record(rid == OFFICIAL_ID, "manifest replace_id is official ccdaa114", str(rid))
    record(man.get("template_data_bucket_url") == "official_asset/template/RF_Kitchen_0302_Scene",
           "template bucket path RF_Kitchen_0302_Scene", str(man.get("template_data_bucket_url")))
    fix_res = FIX.resolve()
    m2_dirs = [ROOT / "tools/scene-template/fixtures", ROOT / "tools/cloud-service/poc-out/fridge"]
    sep = all(not str(fix_res).startswith(str(d.resolve())) for d in m2_dirs)
    record(sep, "fixture dir separate from M2 fixture dirs")
    m2_hits = subprocess.run(["grep", "-rlF", M2_ID, str(FIX)], capture_output=True, text=True).stdout.split()
    record(not m2_hits, "M2 replace_id c83a2f4a absent from official fixture", f"hits={m2_hits[:3]}")

    refs = man.get("references") or {}
    misses = refs.get("missing") or []
    record(refs.get("texture_refs", 0) > 0, "shell texture references enumerated", f"n={refs.get('texture_refs')}")
    record(len(misses) == 0, "zero referenced texture/mesh misses for shell", f"missing={misses[:5]}")
    # independent re-scan of local files vs references
    local = {it["source_key"] for it in files}
    unresolved = [k for k in (refs.get("all_keys") or []) if k not in local]
    record(not unresolved, "every referenced key present in manifest", f"unresolved={unresolved[:5]}")

    envs = man.get("environment") or []
    record(len(envs) > 0, "environment entries recorded", f"n={len(envs)}")
    for e in envs:
        size = e.get("size") or 0
        if e.get("placeholder_not_used"):
            record(not e.get("used", False), f"HDRI placeholder marked & unused {e.get('name')}", f"size={size}")
        else:
            record(size > HDRI_MIN, f"HDRI real (>100KB) {e.get('name')}", f"size={size}")
    record(any(e.get("used") and (e.get("size") or 0) > HDRI_MIN for e in envs) or man.get("environment_none_used_reason"),
           "a real HDRI is used or reason recorded")

    return 1 if fail else 0


if __name__ == "__main__":
    rc = main()
    secret_scan()  # always runs, even when the pull is missing
    print(f"SUMMARY  fail={fail}")
    sys.exit(1 if (rc or fail) else 0)
