#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path

SCENE_ID = "1d0db88a-5a8b-441a-a9f4-b70c2b26fe3a"
TASK_ID = "2aa0b2f5-f10a-4ad2-af4d-944b2398cb36"
VIEW_ID = "298cfe60-923d-44fb-a0d1-f2206b9a48e1"
ENV_ID = "e73ef7d9-ab18-4108-bdbf-3742e4594801"
BODY_ASSET_ID = "bff45e68-6149-4bd7-b048-a6fe4458f01a"
DOOR_ASSET_ID = "38c97cce-169a-4d5c-994c-3c9521ad9f41"
REQUIRED_SUFFIXES = (
    "official_asset/environment/0d718b1b-976d-4225-8ce6-ae514f45eea9/textures/16.exr",
    "official_asset/good_templates/Empty_file/textures/GradientTexture0.tga",
    "official_asset/material/ea684aef-b2c2-4b12-b264-27449c21c5ed/textures/T_MetalWear_Frosted_N.exr",
    "official_asset/material/ea684aef-b2c2-4b12-b264-27449c21c5ed/textures/T_MetalWear_Frosted_R.exr",
    "official_asset/material/ede95c7f-fb5d-44d6-abad-cb9458616a90/textures/T_MetalWear_Frosted_N.exr",
    "official_asset/material/ede95c7f-fb5d-44d6-abad-cb9458616a90/textures/T_MetalWear_Frosted_R.exr",
    "official_asset/material/f7b081d4-c512-4f09-9452-bb130deafd74/textures/T_Mask_03.png",
)


def find_scene(root: Path) -> Path | None:
    preferred = root / "customer_asset" / SCENE_ID / "scene.json"
    if preferred.exists():
        return preferred
    candidates = sorted(root.glob("customer_asset/*/scene.json"))
    return candidates[0] if candidates else None


def assets_complete(root: Path, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_note = 0.0
    while True:
        glb_count = len(list(root.glob("customer_asset/*/models/*.glb")))
        scene_path = find_scene(root)
        required_missing = [name for name in REQUIRED_SUFFIXES if not (root / name).exists()]
        body_glb_count = len(list((root / "customer_asset" / BODY_ASSET_ID / "models").glob("*.glb")))
        door_glb_count = len(list((root / "customer_asset" / DOOR_ASSET_ID / "models").glob("*.glb")))
        if glb_count >= 400 and scene_path and not required_missing and body_glb_count and door_glb_count:
            return
        now = time.monotonic()
        if now - last_note >= 10:
            last_note = now
            print(
                f"waiting: glb={glb_count} body={body_glb_count} door={door_glb_count} "
                f"scene={scene_path is not None} required_missing={len(required_missing)}",
                file=sys.stderr,
                flush=True,
            )
        if now >= deadline:
            raise RuntimeError(
                f"assets incomplete after {timeout_seconds}s: glb={glb_count}, "
                f"scene={scene_path}, required_missing={required_missing}"
            )
        time.sleep(2)


def collect_reference_urls(scene: dict) -> list[str]:
    textures = scene.get("textures", {})
    urls = []
    for mesh in scene.get("meshes", {}).values():
        if isinstance(mesh, dict) and mesh.get("url"):
            urls.append(mesh["url"])
    for texture in textures.values():
        if isinstance(texture, dict) and texture.get("urls"):
            urls.append(texture["urls"])
    for environment in scene.get("environments", {}).values():
        texture_id = environment.get("settings", {}).get("image")
        texture = textures.get(texture_id)
        if isinstance(texture, dict) and texture.get("urls"):
            urls.append(texture["urls"])
    texture_slots = ("roughness_tex", "normal_tex", "basecolor_tex", "mask_tex", "anisotropy_tex")
    for material in scene.get("materials", {}).values():
        for slot in texture_slots:
            texture = textures.get(material.get(slot))
            if isinstance(texture, dict) and texture.get("urls"):
                urls.append(texture["urls"])
    return sorted(set(urls))


def visible_mesh_urls(scene: dict) -> list[str]:
    models = scene.get("models", {})
    meshes = scene.get("meshes", {})
    visited = set()
    urls = []

    def walk(model_id: str, parent_visible: bool = True) -> None:
        if model_id in visited:
            return
        entity = models.get(model_id)
        if not isinstance(entity, dict):
            return
        visited.add(model_id)
        visible = parent_visible and entity.get("is_visible", True) is not False
        if entity.get("type") == "model":
            mesh = meshes.get(entity.get("mesh"))
            if visible and isinstance(mesh, dict) and mesh.get("url"):
                urls.append(mesh["url"])
        for child in entity.get("children", []):
            if isinstance(child, str):
                walk(child, visible)

    for model_id, entity in models.items():
        if isinstance(entity, dict) and entity.get("type") == "root":
            walk(model_id)
    return urls


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare(assets_root: Path, timeout_seconds: int) -> int:
    assets_complete(assets_root, timeout_seconds)
    scene_path = find_scene(assets_root)
    if not scene_path:
        raise RuntimeError("scene.json not found")
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    previous_scene_env = scene.get("scene_settings", {}).get("active_environment")
    previous_front_env = scene.get("views", {}).get(VIEW_ID, {}).get("active_environment")
    scene.setdefault("scene_settings", {})["active_environment"] = ENV_ID
    scene.setdefault("views", {}).setdefault(VIEW_ID, {})["active_environment"] = ENV_ID

    snapshot_path = assets_root.parent / "stage-fridge-scene_snapshot.json"
    write_json(snapshot_path, scene)

    asset_map = {}
    for path in sorted(assets_root.rglob("*")):
        if path.is_file():
            asset_map[path.relative_to(assets_root).as_posix()] = str(path.resolve())
    assets_path = assets_root.parent / "stage-fridge-assets.json"
    write_json(assets_path, asset_map)

    referenced_urls = collect_reference_urls(scene)
    missing = [url for url in referenced_urls if url not in asset_map]
    visible_urls = visible_mesh_urls(scene)
    missing_visible = sorted(set(visible_urls) - set(asset_map))
    glb_count = sum(path.suffix.lower() == ".glb" for path in assets_root.rglob("*") if path.is_file())
    texture_count = sum(
        path.suffix.lower() in {".png", ".jpg", ".jpeg", ".exr", ".tga", ".webp"}
        for path in assets_root.rglob("*")
        if path.is_file()
    )
    materials = scene.get("materials", {})
    texture_slots = ("roughness_tex", "normal_tex", "basecolor_tex", "mask_tex", "anisotropy_tex")
    materials_with_textures = [
        material_id for material_id, material in materials.items()
        if any(material.get(slot) for slot in texture_slots)
    ]
    meta = {
        "task_id": TASK_ID,
        "scene_id": SCENE_ID,
        "view_id": VIEW_ID,
        "view_name": scene.get("views", {}).get(VIEW_ID, {}).get("name"),
        "active_camera": scene.get("views", {}).get(VIEW_ID, {}).get("active_camera"),
        "active_environment": ENV_ID,
        "previous_scene_environment": previous_scene_env,
        "previous_front_environment": previous_front_env,
        "scene_path": str(scene_path.resolve()),
        "scene_snapshot_path": str(snapshot_path.resolve()),
        "assets_root": str(assets_root.resolve()),
        "asset_map_path": str(assets_path.resolve()),
        "asset_count": len(asset_map),
        "glb_count": glb_count,
        "texture_count": texture_count,
        "material_count": len(materials),
        "materials_with_texture_slots": len(materials_with_textures),
        "referenced_asset_count": len(referenced_urls),
        "missing_asset_count": len(missing),
        "missing_assets": missing,
        "visible_mesh_count": len(visible_urls),
        "missing_visible_asset_count": len(missing_visible),
        "missing_visible_assets": missing_visible,
        "required_assets": {name: (assets_root / name).exists() for name in REQUIRED_SUFFIXES},
    }
    write_json(assets_root.parent / "stage-fridge-meta.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-root", type=Path, default=Path(__file__).parent / "assets")
    parser.add_argument("--wait-timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    return prepare(args.assets_root, args.wait_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
