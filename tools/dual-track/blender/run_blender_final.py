#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import tempfile


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render one stage view with the folded-in Blender final track."
    )
    parser.add_argument("--scene", required=True)
    parser.add_argument("--asset-map", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--view", required=True)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--spp", type=int, default=32)
    parser.add_argument(
        "--view-transform",
        default="Standard",
        help="Blender color-management view transform. Default stays Standard; pass AgX only as an override.",
    )
    parser.add_argument("--denoise", choices=("0", "1"), default="1")
    parser.add_argument("--mask-out")
    parser.add_argument("--light-scale", type=float)
    parser.add_argument("--sky-scale", type=float)
    parser.add_argument("--hdri-reflection", type=float)
    parser.add_argument("--exposure-bias", type=float)
    parser.add_argument("--drawer-albedo", type=float)
    parser.add_argument("--charcoal-albedo", type=float)
    parser.add_argument("--edge-left-albedo", type=float)
    parser.add_argument("--edge-left-roughness", type=float)
    parser.add_argument("--edge-left-metalness", type=float)
    parser.add_argument("--edge-right-albedo", type=float)
    parser.add_argument("--edge-right-roughness", type=float)
    parser.add_argument("--edge-right-metalness", type=float)
    parser.add_argument("--interior-lift", type=float)
    parser.add_argument("--flake", type=float)
    parser.add_argument("--fill-scale", type=float)
    parser.add_argument("--interior-emit-z0", type=float)
    parser.add_argument("--interior-emit-z1", type=float)
    parser.add_argument("--interior-emit", type=float)
    parser.add_argument("--interior-lift-low", type=float)
    parser.add_argument("--interior-split-y", type=float)
    parser.add_argument("--edge-left-specular", type=float)
    parser.add_argument("--edge-right-specular", type=float)
    parser.add_argument(
        "--tonemap",
        choices=("none", "ue-filmic", "ue55"),
        help="Opt-in UE-like post + filmic on linear EXR. Omitted = Standard path unchanged.",
    )
    parser.add_argument("--fallback-light", choices=("0", "1"))
    parser.add_argument("--linear-out")
    parser.add_argument("--env-mode", choices=("legacy", "ue"), help="r7 opt-in: UE white backdrop + 4.exr SkyLight.")
    parser.add_argument("--skylight-scale", type=float)
    parser.add_argument("--white-sky-scale", type=float)
    parser.add_argument("--hdri-mirror", choices=("0", "1"))
    parser.add_argument("--material-mode", choices=("legacy", "stage"), help="r7 opt-in: scene JSON material values, no hacks.")
    parser.add_argument("--glass-mode", choices=("solid", "thin"))
    parser.add_argument("--light-units", choices=("legacy", "candela"), help="r8 opt-in: UE Candelas -> Cycles Watts.")
    parser.add_argument("--display-units", choices=("legacy", "engine"), help="r12 opt-in: UE 5.5.4 source-verified display scale (nits*0.18*2**bias).")
    parser.add_argument("--hdri-angle", help='Opt-in HDRI Z rotation: "scene" or degrees. Omitted = unrotated (default).')
    parser.add_argument(
        "--blender",
        default=(
            "/Applications/Blender.app/Contents/MacOS/Blender"
            if sys.platform == "darwin"
            else "blender"
        ),
    )
    return parser.parse_args()


def load_asset_map(path):
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    if isinstance(raw, dict):
        entries = raw.items()
    elif isinstance(raw, list):
        entries = []
        for item in raw:
            if not isinstance(item, dict) or "key" not in item or "value" not in item:
                raise ValueError("Asset map entries require key and value")
            entries.append((item["key"], item["value"]))
    else:
        raise ValueError("Asset map must be an object or an entry list")
    return dict(entries)


def resolve_asset_path(value, assets_root, map_directory):
    candidates = []
    if os.path.isabs(value):
        candidates.append(value)
    else:
        if assets_root:
            candidates.append(os.path.join(assets_root, value))
        candidates.extend(
            (
                os.path.join(map_directory, value),
                os.path.join(map_directory, os.path.basename(value)),
            )
        )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise FileNotFoundError(value)


def required_urls(scene):
    urls = set()
    for mesh in (scene.get("meshes") or {}).values():
        if mesh.get("url"):
            urls.add(mesh["url"])
    for view in (scene.get("views") or {}).values():
        environment = (scene.get("environments") or {}).get(
            view.get("active_environment")
        )
        texture_id = (environment or {}).get("settings", {}).get("image")
        texture = (scene.get("textures") or {}).get(texture_id)
        texture_url = texture and (texture.get("urls") or texture.get("url"))
        if texture_url:
            urls.add(texture_url)
    return urls


def prepare_assets(scene, map_path, assets_root):
    map_directory = os.path.dirname(os.path.abspath(map_path))
    asset_map = load_asset_map(map_path)
    urls = required_urls(scene)
    missing = sorted(urls - asset_map.keys())
    if missing:
        print(
            f"[assets] {len(missing)} scene URLs absent from asset map; skipping",
            flush=True,
        )
    resolved = {}
    for url in sorted(urls & asset_map.keys()):
        try:
            resolved[url] = resolve_asset_path(
                asset_map[url], assets_root, map_directory
            )
        except FileNotFoundError as error:
            print(f"[assets] {error} unreachable; skipping", flush=True)
    return resolved


def main():
    args = parse_args()
    with open(args.scene, encoding="utf-8") as stream:
        scene = json.load(stream)
    scene = scene.get("scene_json", scene)
    assets = prepare_assets(scene, args.asset_map, os.environ.get("DUAL_TRACK_ASSETS_ROOT"))
    output = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    assets_path = None
    temporary_directory = tempfile.TemporaryDirectory(prefix="mutracer-final-")
    try:
        assets_path = os.path.join(temporary_directory.name, "assets.json")
        with open(assets_path, "w", encoding="utf-8") as stream:
            json.dump(assets, stream)
        command = [
            args.blender,
            "--background",
            "--factory-startup",
            "--python",
            os.path.abspath(os.path.join(__file__, "..", "blender_inner.py")),
            "--",
            "--scene",
            os.path.abspath(args.scene),
            "--assets-file",
            assets_path,
            "--view",
            args.view,
            "--out",
            output,
            "--spp",
            str(args.spp),
            "--denoise",
            args.denoise,
            "--view-transform",
            args.view_transform or "Standard",
        ]
        if args.mask_out:
            command.extend(("--mask-out", os.path.abspath(args.mask_out)))
        for flag, value in (
            ("--light-scale", args.light_scale),
            ("--sky-scale", args.sky_scale),
            ("--hdri-reflection", args.hdri_reflection),
            ("--exposure-bias", args.exposure_bias),
            ("--drawer-albedo", args.drawer_albedo),
            ("--charcoal-albedo", args.charcoal_albedo),
            ("--edge-left-albedo", args.edge_left_albedo),
            ("--edge-left-roughness", args.edge_left_roughness),
            ("--edge-left-metalness", args.edge_left_metalness),
            ("--edge-right-albedo", args.edge_right_albedo),
            ("--edge-right-roughness", args.edge_right_roughness),
            ("--edge-right-metalness", args.edge_right_metalness),
            ("--interior-lift", args.interior_lift),
            ("--flake", args.flake),
            ("--fill-scale", args.fill_scale),
            ("--interior-emit-z0", args.interior_emit_z0),
            ("--interior-emit-z1", args.interior_emit_z1),
            ("--interior-emit", args.interior_emit),
            ("--interior-lift-low", args.interior_lift_low),
            ("--interior-split-y", args.interior_split_y),
            ("--edge-left-specular", args.edge_left_specular),
            ("--edge-right-specular", args.edge_right_specular),
            ("--tonemap", args.tonemap),
            ("--fallback-light", args.fallback_light),
            ("--linear-out", args.linear_out and os.path.abspath(args.linear_out)),
            ("--hdri-angle", args.hdri_angle),
            ("--env-mode", args.env_mode),
            ("--skylight-scale", args.skylight_scale),
            ("--white-sky-scale", args.white_sky_scale),
            ("--hdri-mirror", args.hdri_mirror),
            ("--material-mode", args.material_mode),
            ("--glass-mode", args.glass_mode),
            ("--light-units", args.light_units),
            ("--display-units", args.display_units),
        ):
            if value is not None:
                command.extend((flag, str(value)))
        if args.width:
            command.extend(("--width", str(args.width)))
        if args.height:
            command.extend(("--height", str(args.height)))
        subprocess.run(command, check=True)
    finally:
        temporary_directory.cleanup()
    print(output)


if __name__ == "__main__":
    main()
