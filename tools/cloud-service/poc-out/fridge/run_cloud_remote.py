from __future__ import annotations
#!/usr/bin/env python3
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ASSETS_ROOT = Path("/tmp/mutracer-fridge-assets")
SCENE_OVERRIDE = Path("/tmp/stage-fridge-scene_snapshot.json")
SCENE_ID = "1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a"
VIEW_ID = "298cfe60-923d-44fb-a0d1-f2206b9a48e1"
ENV_ID = "ab403659-925e-41d7-abed-17d9e0e107f2"
API_BASE = "http://127.0.0.1:8787"
PARAMS = {
    "view": VIEW_ID,
    "width": 960,
    "height": 540,
    "samples": 64,
    "bounces": 4,
    "denoise": True,
    "timeout_ms": 600000,
    "tone_mapping": "agx",
    "light_scale": 1,
}


def note(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def request_json(path: str, payload: dict | None = None, timeout: int = 120) -> tuple[int, object]:
    token = os.environ["MUTRACER_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API_BASE + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} HTTP {error.code}: {body}") from error


def collect_reference_urls(scene: dict) -> list[str]:
    textures = scene.get("textures", {})
    urls = set()
    for mesh in scene.get("meshes", {}).values():
        if isinstance(mesh, dict) and mesh.get("url"):
            urls.add(mesh["url"])
    for texture in textures.values():
        if isinstance(texture, dict) and texture.get("urls"):
            urls.add(texture["urls"])
    for environment in scene.get("environments", {}).values():
        texture = textures.get(environment.get("settings", {}).get("image"))
        if isinstance(texture, dict) and texture.get("urls"):
            urls.add(texture["urls"])
    for material in scene.get("materials", {}).values():
        for slot in ("roughness_tex", "normal_tex", "basecolor_tex", "mask_tex", "anisotropy_tex"):
            texture = textures.get(material.get(slot))
            if isinstance(texture, dict) and texture.get("urls"):
                urls.add(texture["urls"])
    return sorted(urls)


def build_payload() -> dict:
    scene_path = SCENE_OVERRIDE if SCENE_OVERRIDE.exists() else (ASSETS_ROOT / "customer_asset" / SCENE_ID / "scene.json")
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    scene.setdefault("scene_settings", {})["active_environment"] = ENV_ID
    scene.setdefault("views", {}).setdefault(VIEW_ID, {})["active_environment"] = ENV_ID
    referenced = collect_reference_urls(scene)
    assets = {}
    for path in sorted(ASSETS_ROOT.rglob("*")):
        if path.is_file():
            key = path.relative_to(ASSETS_ROOT).as_posix()
            assets[key] = base64.b64encode(path.read_bytes()).decode("ascii")
    missing = [url for url in referenced if url not in assets]
    note(f"cloud_payload asset_count={len(assets)} referenced={len(referenced)} missing={len(missing)}")
    # Only require assets for currently visible model meshes; ignore hidden closed-door packs.
    visible_mesh_urls=set()
    models=scene.get("models") or {}
    meshes=scene.get("meshes") or {}
    def walk(nid, parent_vis=True):
        node=models.get(nid)
        if not node: return
        vis=node.get("is_visible")
        vis=True if vis is None else bool(vis)
        if not (parent_vis and vis): return
        if node.get("type")=="model" and node.get("mesh"):
            mesh=meshes.get(node["mesh"]) or {}
            if mesh.get("url"): visible_mesh_urls.add(mesh["url"])
        for child in node.get("children") or []:
            walk(child, True)
    for mid,node in models.items():
        if node.get("type")=="root":
            walk(mid)
    mesh_missing=sorted(u for u in visible_mesh_urls if u not in assets)
    if mesh_missing:
        raise RuntimeError(f"missing visible mesh assets: {mesh_missing[:8]}")
    if missing:
        note(f"cloud_payload soft_missing_non_visible={len(missing)}")
    return {"kind": "render", "scene": scene, "assets": assets, "params": PARAMS}


def main() -> None:
    payload = build_payload()
    status, response = request_json("/v1/jobs", payload, timeout=300)
    if status != 201:
        raise RuntimeError(f"job creation returned {status}")
    job_id = response["id"]
    note(f"cloud_job_id={job_id}")
    deadline = time.monotonic() + 900
    while True:
        _, job = request_json(f"/v1/jobs/{job_id}", timeout=30)
        note(f"cloud_status={job['status']}")
        if job["status"] == "succeed":
            break
        if job["status"] == "failed":
            raise RuntimeError(job.get("error") or "cloud job failed")
        if time.monotonic() >= deadline:
            raise RuntimeError("cloud job timed out after 900s")
        time.sleep(2)
    token = os.environ["MUTRACER_API_TOKEN"]
    request = urllib.request.Request(
        f"{API_BASE}/v1/jobs/{job_id}/render.png",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        sys.stdout.buffer.write(response.read())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        note(f"cloud_error={error}")
        raise
