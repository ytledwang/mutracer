#!/usr/bin/env python3
"""GET only the explicit missing assets needed for r8 Front/前视图 renders.
Host is http://10.160.9.143:8000 only. Anon key stays in memory via official_pull_lib.
customer_asset only via get_allowlisted_object with an explicit allowlist.
Never lists a bucket. Never prints secrets. Stop the whole run on TCP/timeout.
"""
from __future__ import annotations
import json, os, sys, hashlib, socket
from pathlib import Path
from urllib.error import URLError

os.environ["OFFICIAL_PULL_BASE"] = "http://10.160.9.143:8000"
sys.path.insert(0, "/Users/wangjianzheng/Project/git/mutracer/tools/fusion-checks")
from official_pull_lib import Client

REPO = Path("/Users/wangjianzheng/Project/git/mutracer")
R8 = REPO / "docs/prd/evidence/fusion/fidelity/r8"
DEST_ROOT = REPO / "tools/cloud-service/poc-out/r8-assets"
OLD_MAP = REPO / "docs/prd/evidence/fusion/fidelity/r3/official-assets.json"
NEW_MAP = R8 / "assets.json"
NEEDED_LIST = R8 / "needed-assets.json"
ALLOWLIST_PATH = R8 / "customer-allowlist.txt"

# Front/前视图 needed URLs that are not already in the official kitchen map.
# Built from scene meshes/materials/env of the selected view only.
NEEDED = [
    # pillow Front
    "customer_asset/1420cf60-cf8a-4445-94a6-a6f6fb1c00f9/models/b2257a9a-761f-4522-ae54-3ff96a848cae.glb",
    "official_asset/material/3143c322-4a04-4e5e-8ac1-22449517e438/textures/T_HerringboneChecker_BC.png",
    "official_asset/material/3143c322-4a04-4e5e-8ac1-22449517e438/textures/T_HerringboneChecker_N.png",
    "official_asset/material/3143c322-4a04-4e5e-8ac1-22449517e438/textures/T_HerringboneChecker_R.png",
    # stove 前视图 (White.exr + visible meshes/textures). HDRI brown already in old map for pillow/hood.
    "official_asset/template/Product_ZJG_5cam/models/dike.glb",
    "official_asset/template/Product_ZJG_5cam/models/xianshi.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_001.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_003.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_19.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_23.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_24.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_28.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbiananniu_3.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbinzaomian_12.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbinzaomian_13.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbinzaomian_18.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbinzaomian_26.glb",
    "official_asset/template/Product_ZJG_5cam/models/youbinzaomian_7.glb",
    "official_asset/template/Product_ZJG_5cam/models/youcetiezhi.glb",
    "official_asset/template/Product_ZJG_5cam/models/zaojumian.glb",
    "official_asset/template/Product_ZJG_5cam/models/zaojuqian.glb",
    "official_asset/template/Product_ZJG_5cam/models/zaomianxia.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobiananniu_1.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobiananniu_11.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobiananniu_22.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobiananniu_27.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobiananniu_28.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobiananniu_8.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobianzaomian_5.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuobianzaomian_9.glb",
    "official_asset/template/Product_ZJG_5cam/models/zuocetiezhi.glb",
    "official_asset/template/Product_ZJG_5cam/textures/T_MetalWear_Lines_N.exr",
    "official_asset/template/Product_ZJG_5cam/textures/T_MetalWear_Lines_R.exr",
    "official_asset/template/Product_ZJG_5cam/textures/T_MetalWear_Wear03_R.exr",
    "official_asset/template/Product_ZJG_5cam/textures/T_Metal_Painted_R.png",
    "official_asset/template/Product_ZJG_5cam/textures/T_White_Color.png",
    "official_asset/template/Product_ZJG_5cam/textures/White.exr",
    "official_asset/template/Product_ZJG_5cam/textures/XYJHW10x_diff.png",
    "official_asset/template/Product_ZJG_5cam/textures/ZT_UI_A.png",
    "official_asset/template/Product_ZJG_5cam/textures/ZY_1.png",
    "official_asset/template/Product_ZJG_5cam/textures/ZY_1__Mask.png",
    # hood Front visible meshes
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/06a71876-4c39-4d66-a66a-b13cb52e7bc3.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/098c71d1-71cd-486f-973b-4b92ec8cf975.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/0de1de51-9bbf-47b5-9ce1-28927161171f.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/1ca27801-9cd2-46dc-99e4-0d33073b6509.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/4366169a-edaf-4839-93e5-d302d6b201a9.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/4f082bb7-97ec-43b6-b2e2-da6207233e4f.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/5046f278-5d82-45c0-a2eb-0eb94c749f91.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/5f2253e4-da24-4881-aade-a0483f8c3349.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/63618d12-bf67-4cb2-904d-fbde9f9a172a.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/65751d9b-fccb-4671-92a9-e87a487dca02.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/7558620e-b608-4cf2-9c1e-a3429d976b7f.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/75d8bb48-1ec6-4176-98f9-b1c3bb4e5914.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/8839ce32-fe87-42d9-91dc-9e0c2afa6ab6.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/9089c078-5877-4a4d-8c24-63810f0f5ec6.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/960905e7-19c7-470c-a1ca-a9d441dd780c.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/af75fb13-155e-4987-ba86-a652a5451f66.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/c4f5e7b7-0a79-4164-a4e7-9b8396e0d17b.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/cc189264-edfd-4687-8be5-44021ff9df47.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/ce56a775-1491-4f56-990d-106a5037e05e.glb",
    "customer_asset/00ee50b7-87bc-4645-b899-7b9ecb6ba2cc/models/df719308-14ee-4ba0-b148-2b30d40275f4.glb",
]


def looks_ok(key: str, data: bytes) -> str | None:
    if len(data) < 8:
        return f"too small ({len(data)} bytes)"
    if key.endswith(".png") and not data.startswith(b"\x89PNG"):
        return "not a PNG header"
    if key.endswith(".glb") and not data.startswith(b"glTF"):
        return "not a GLB/glTF header"
    if key.endswith(".exr") and data[:4] not in (b"\x76\x2f\x31\x01", b"v/1\x01"):
        return "not an EXR header"
    return None


def is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionError)):
        return True
    if isinstance(exc, URLError):
        return True
    name = type(exc).__name__
    if name in {"TimeoutError", "URLError", "ConnectionError", "OSError", "socket.timeout"}:
        return True
    msg = str(exc).lower()
    return any(s in msg for s in ("timed out", "timeout", "connection refused", "network is unreachable", "nodename nor servname", "connection reset"))


def main() -> int:
    client = Client(".env.production")
    if client.host != "10.160.9.143:8000" or not client.base.startswith("http://10.160.9.143"):
        print(f"FAIL unexpected host {client.host}")
        return 1
    amap = json.loads(OLD_MAP.read_text())
    if NEW_MAP.exists():
        amap.update(json.loads(NEW_MAP.read_text()))
    allowlist = {k for k in NEEDED if k.startswith("customer_asset/")}
    ALLOWLIST_PATH.write_text("\n".join(sorted(allowlist)) + "\n")
    results = []
    failed = 0
    skipped = 0
    fetched = 0
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    for key in NEEDED:
        if key in amap and Path(amap[key]).is_file() and Path(amap[key]).stat().st_size > 8:
            results.append({"key": key, "status": "already_local", "path": amap[key], "bytes": Path(amap[key]).stat().st_size})
            skipped += 1
            print(f"SKIP already {key}")
            continue
        dest = DEST_ROOT / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if key.startswith("customer_asset/"):
                data = client.get_allowlisted_object(key, allowlist)
            elif key.startswith("official_asset/"):
                data = client.get_object("official_asset", key[len("official_asset/"):])
            else:
                print(f"FAIL unexpected bucket {key}")
                return 1
        except Exception as e:
            msg = str(e)
            if "eyJ" in msg:
                msg = msg.split("eyJ")[0] + "[redacted]"
            if is_transport_error(e):
                print(f"STOP transport error on {key}: {type(e).__name__}: {msg[:240]}")
                return 2
            print(f"FAIL {key}: {type(e).__name__}: {msg[:240]}")
            results.append({"key": key, "status": "FAIL", "error": f"{type(e).__name__}: {msg[:240]}"})
            failed += 1
            continue
        err = looks_ok(key, data)
        if err:
            print(f"FAIL {key}: {err} bytes={len(data)}")
            results.append({"key": key, "status": "FAIL", "error": err, "bytes": len(data)})
            failed += 1
            continue
        dest.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        amap[key] = str(dest)
        fetched += 1
        results.append({"key": key, "status": "OK", "bytes": len(data), "sha256": sha, "path": str(dest)})
        print(f"OK {key} bytes={len(data)} sha256={sha}")
    NEW_MAP.write_text(json.dumps(amap, ensure_ascii=False, indent=1) + "\n")
    NEEDED_LIST.write_text(json.dumps({
        "host": "http://10.160.9.143:8000",
        "n_needed": len(NEEDED),
        "n_fetched": fetched,
        "n_already_local": skipped,
        "n_failed": failed,
        "customer_allowlist": sorted(allowlist),
        "results": results,
    }, ensure_ascii=False, indent=1) + "\n")
    print(f"DONE fetched={fetched} skipped={skipped} failed={failed} map={NEW_MAP}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
