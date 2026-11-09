#!/usr/bin/env python3
import argparse
import copy
import json
import os
import subprocess
import sys
import time

import numpy
from PIL import Image


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREVIEW_BINARY = os.path.join(
    REPO_ROOT, "native/host/target/release/mutracer-render"
)
FINAL_SCRIPT = os.path.join(
    REPO_ROOT, "tools/dual-track/blender/run_blender_final.py"
)
DEFAULT_REF = os.path.join(
    REPO_ROOT,
    "tools/cloud-service/poc-out/fridge/ref/fridge-ref-front-329c-1024.png",
)
BLENDER_BINARY = (
    "/Applications/Blender.app/Contents/MacOS/Blender"
    if sys.platform == "darwin"
    else "blender"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render one stage scene through preview and/or Blender final tracks."
    )
    parser.add_argument("mode", choices=("preview", "final", "both"))
    parser.add_argument("--scene", required=True)
    parser.add_argument("--asset-map", required=True)
    parser.add_argument("--assets-root")
    parser.add_argument("--view")
    parser.add_argument("--views", help="comma-separated view ids")
    parser.add_argument(
        "--all-views",
        action="store_true",
        help="render every view of --scene (render_settings.views_in_task first)",
    )
    parser.add_argument("--preview-out")
    parser.add_argument("--preview-width", type=int, default=960)
    parser.add_argument("--preview-height", type=int, default=540)
    parser.add_argument("--preview-spp", type=int, default=32)
    parser.add_argument("--preview-bounces", type=int, default=8)
    parser.add_argument("--oidn-library")
    parser.add_argument("--final-out")
    parser.add_argument("--final-width", type=int, default=1920)
    parser.add_argument("--final-height", type=int, default=1080)
    parser.add_argument("--final-spp", type=int, default=512)
    parser.add_argument("--final-mask-out")
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
    parser.add_argument("--denoise", choices=("0", "1"), default="1")
    parser.add_argument("--compare-out")
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF if os.path.isfile(DEFAULT_REF) else None,
    )
    parser.add_argument("--metrics-out")
    parser.add_argument("--preview-binary", default=PREVIEW_BINARY)
    parser.add_argument("--blender", default=BLENDER_BINARY)
    args = parser.parse_args()
    if not (args.view or args.views or args.all_views):
        parser.error("one of --view, --views or --all-views is required")
    if args.mode == "preview":
        args.preview_out = args.preview_out or "preview.png"
    elif args.mode == "final":
        args.final_out = args.final_out or "final.png"
    else:
        args.preview_out = args.preview_out or "preview.png"
        args.final_out = args.final_out or "final.png"
    if args.compare_out and not args.metrics_out:
        args.metrics_out = os.path.join(
            os.path.dirname(os.path.abspath(args.compare_out)), "arch-metrics.json"
        )
    return args


def scene_view_ids(scene_path):
    with open(scene_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    source = data.get("scene_json", data)
    for container in (data, source):
        settings = container.get("render_settings")
        listed = settings.get("views_in_task") if isinstance(settings, dict) else None
        if listed:
            ids = [
                item.get("id") if isinstance(item, dict) else item for item in listed
            ]
            ids = [str(view) for view in ids if view]
            if ids:
                return ids
    views = source.get("views")
    if isinstance(views, dict):
        return list(views)
    if isinstance(views, list):
        return [
            str(view["id"]) for view in views if isinstance(view, dict) and view.get("id")
        ]
    raise SystemExit(f"no views found in {scene_path}")


def resolve_views(args):
    if args.all_views:
        return scene_view_ids(args.scene)
    if args.views:
        return [view.strip() for view in args.views.split(",") if view.strip()]
    return [args.view]


def suffixed(path, view):
    if not path:
        return path
    stem, extension = os.path.splitext(path)
    return f"{stem}-{view[:8]}{extension}"


def run(command):
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def render_preview(args):
    output = os.path.abspath(args.preview_out)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    command = [
        args.preview_binary,
        "--scene",
        args.scene,
        "--out",
        output,
        "--asset-map",
        args.asset_map,
        "--view",
        args.view,
        "--width",
        str(args.preview_width),
        "--height",
        str(args.preview_height),
        "--samples",
        str(args.preview_spp),
        "--bounces",
        str(args.preview_bounces),
        "--denoise",
        args.denoise,
        "--timeout-ms",
        "600000",
    ]
    if args.oidn_library:
        command.extend(("--oidn-library", os.path.abspath(args.oidn_library)))
    started = time.monotonic()
    run(command)
    return output, time.monotonic() - started


def render_final(args):
    output = os.path.abspath(args.final_out)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    command = [
        sys.executable,
        FINAL_SCRIPT,
        "--scene",
        args.scene,
        "--asset-map",
        args.asset_map,
        "--out",
        output,
        "--view",
        args.view,
        "--width",
        str(args.final_width),
        "--height",
        str(args.final_height),
        "--spp",
        str(args.final_spp),
        "--denoise",
        args.denoise,
        "--blender",
        args.blender,
    ]
    if args.final_mask_out:
        command.extend(("--mask-out", os.path.abspath(args.final_mask_out)))
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
    ):
        if value is not None:
            command.extend((flag, str(value)))
    if args.assets_root:
        env = os.environ.copy()
        env["DUAL_TRACK_ASSETS_ROOT"] = os.path.abspath(args.assets_root)
        started = time.monotonic()
        subprocess.run(command, check=True, env=env)
        return output, time.monotonic() - started
    started = time.monotonic()
    run(command)
    return output, time.monotonic() - started


def brightness_standard_deviation(image):
    gray = image.convert("L")
    histogram = gray.histogram()
    count = sum(histogram)
    mean = sum(index * value for index, value in enumerate(histogram)) / count
    variance = (
        sum(value * (index - mean) ** 2 for index, value in enumerate(histogram)) / count
    )
    return variance ** 0.5


def background_color(image):
    corners = (
        image.getpixel((2, 2)),
        image.getpixel((image.width - 3, 2)),
        image.getpixel((2, image.height - 3)),
        image.getpixel((image.width - 3, image.height - 3)),
    )
    return tuple(
        sorted(pixel[channel] for pixel in corners)[1] for channel in range(3)
    )


def silhouette(image, background, threshold):
    array = numpy.asarray(image, dtype=numpy.int16)
    difference = numpy.abs(array - numpy.array(background, dtype=numpy.int16))
    # PIL convert("L") weights, so the threshold matches the earlier IoU numbers.
    luma = (
        difference[..., 0] * 299 + difference[..., 1] * 587 + difference[..., 2] * 114
    ) / 1000
    return luma.astype(numpy.uint8) > threshold


def intersection_over_union(left_mask, right_mask):
    union = numpy.logical_or(left_mask, right_mask).sum()
    if not union:
        return 1.0
    return float(numpy.logical_and(left_mask, right_mask).sum() / union)


# Normalized (x0, y0, x1, y1) regions in the 16:9 frame, measured on the
# reference: door edge strips (charcoal, located by scanning the reference for dark runs), top-left lower drawer face,
# bottom drawer face, and the mid body band between the open doors.
REGIONS = {
    "door_edge_left": (0.3215, 0.12, 0.3245, 0.45),
    "door_edge_right": (0.6548, 0.12, 0.6640, 0.45),
    "drawer_upper_left": (0.38, 0.60, 0.48, 0.70),
    "drawer_bottom": (0.38, 0.80, 0.59, 0.92),
    "body_mid_band": (0.40, 0.36, 0.57, 0.52),
}


def region_mean(image, box):
    array = numpy.asarray(image, dtype=numpy.float64)
    height, width = array.shape[:2]
    x0, y0, x1, y1 = box
    crop = array[int(y0 * height):int(y1 * height), int(x0 * width):int(x1 * width)]
    return crop.reshape(-1, 3).mean(axis=0)


def region_metrics(final, reference):
    result = {}
    for name, box in REGIONS.items():
        final_mean = region_mean(final, box)
        entry = {"final_rgb": [round(float(v), 1) for v in final_mean]}
        if reference is not None:
            reference_mean = region_mean(reference, box)
            entry["ref_rgb"] = [round(float(v), 1) for v in reference_mean]
            entry["abs_delta"] = [
                round(float(abs(a - b)), 1) for a, b in zip(final_mean, reference_mean)
            ]
            entry["abs_delta_mean"] = round(float(numpy.abs(final_mean - reference_mean).mean()), 1)
        result[name] = entry
    return result


def compare_and_measure(args, preview_path, final_path):
    preview = Image.open(preview_path).convert("RGB")
    final = Image.open(final_path).convert("RGB")
    reference = Image.open(args.ref).convert("RGB") if args.ref else None
    target_height = min(preview.height, final.height)
    target_height = min(reference.height, 1080) if reference else target_height

    def resized(image):
        width = max(1, round(image.width * target_height / image.height))
        return image.resize((width, target_height), Image.Resampling.LANCZOS)

    preview = resized(preview)
    final = resized(final)
    reference = resized(reference) if reference else None
    images = [preview, final] + ([reference] if reference else [])
    total_width = sum(image.width for image in images) + 2 * (len(images) - 1)
    comparison = Image.new("RGB", (total_width, target_height), "white")
    offset = 0
    for image in images:
        comparison.paste(image, (offset, 0))
        offset += image.width + 2
    comparison_path = os.path.abspath(args.compare_out)
    os.makedirs(os.path.dirname(comparison_path) or ".", exist_ok=True)
    comparison.save(comparison_path)

    threshold = 16
    preview_iou = None
    final_iou = None
    if reference:
        reference_mask = silhouette(reference, background_color(reference), threshold)
        preview_iou = intersection_over_union(
            silhouette(preview, background_color(preview), threshold),
            reference_mask,
        )
        final_iou = intersection_over_union(
            silhouette(final, background_color(final), threshold),
            reference_mask,
        )
    mask_iou = None
    if reference and args.final_mask_out and os.path.isfile(args.final_mask_out):
        mask = Image.open(args.final_mask_out).convert("L")
        mask = mask.resize(reference.size, Image.Resampling.NEAREST)
        mask_iou = intersection_over_union(
            numpy.asarray(mask) > 127,
            silhouette(reference, background_color(reference), threshold),
        )
    metrics = {
        "regions": region_metrics(final, reference),
        "silhouette_iou_mask_final_vs_ref": mask_iou,
        "brightness_std": {
            "preview": brightness_standard_deviation(preview),
            "final": brightness_standard_deviation(final),
            "ref": brightness_standard_deviation(reference) if reference else None,
        },
        "silhouette_iou_preview_vs_ref": preview_iou,
        "silhouette_iou_final_vs_ref": final_iou,
        "threshold": threshold,
    }
    metrics_path = os.path.abspath(args.metrics_out)
    os.makedirs(os.path.dirname(metrics_path) or ".", exist_ok=True)
    with open(metrics_path, "w", encoding="utf-8") as stream:
        json.dump(metrics, stream, indent=2)
        stream.write("\n")
    print(json.dumps(metrics, indent=2))
    return comparison_path, metrics_path


def render_view(args):
    preview_path = None
    final_path = None
    preview_seconds = None
    final_seconds = None
    if args.mode in ("preview", "both"):
        preview_path, preview_seconds = render_preview(args)
    if args.mode in ("final", "both"):
        final_path, final_seconds = render_final(args)
    if args.compare_out:
        if not (preview_path and final_path):
            raise SystemExit("--compare-out requires --mode both")
        compare_and_measure(args, preview_path, final_path)
    return {
        "view": args.view,
        "preview": preview_path,
        "final": final_path,
        "preview_seconds": preview_seconds,
        "final_seconds": final_seconds,
    }


def main():
    args = parse_args()
    views = resolve_views(args)
    results = []
    for view in views:
        view_args = copy.copy(args)
        view_args.view = view
        if len(views) > 1:
            for name in (
                "preview_out",
                "final_out",
                "final_mask_out",
                "compare_out",
                "metrics_out",
            ):
                setattr(view_args, name, suffixed(getattr(args, name), view))
            print(f"== view {view}", flush=True)
        results.append(render_view(view_args))
    if len(results) == 1:
        result = results[0]
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "preview_seconds": result["preview_seconds"],
                    "final_seconds": result["final_seconds"],
                },
                indent=2,
            )
        )
    else:
        print(json.dumps({"mode": args.mode, "views": results}, indent=2))


if __name__ == "__main__":
    main()
