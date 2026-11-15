#!/usr/bin/env python3
"""Official MuTracer GLB export preset. Names are the contract.

Default path keeps mesh/node names, source material names, Pivot nodes,
cameras, and extras (replace_id / placeholders). Draco and meshopt are
allowed; flatten / prune / palette / gltfpack are forbidden.

Can be imported from Blender or run as:
  blender --background --python export_glb_preset.py -- --input in.fbx --output out.glb
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Values the official path always sets. Filtered against the operator RNA
# so a slightly older remote Blender can still export.
EXPORT_GLB_KWARGS = {
    "export_format": "GLB",
    "export_copyright": "mutracer-import-contract",
    "export_texcoords": True,
    "export_normals": True,
    "export_materials": "EXPORT",
    "export_cameras": True,
    "export_extras": True,
    "export_yup": True,
    "export_apply": False,
    "export_animations": True,
    "export_force_sampling": True,
    "export_animation_mode": "ACTIONS",
    "export_lights": False,
    "export_gpu_instances": False,
    "export_hierarchy_flatten_objs": False,
    "export_hierarchy_flatten_bones": False,
    "export_use_gltfpack": False,
    "export_draco_mesh_compression_enable": False,
    "export_unused_images": False,
    "export_gn_mesh": False,
}

# Must stay false / off on the default path. Checked after kwargs are applied.
FORBIDDEN_IF_TRUE = (
    "export_hierarchy_flatten_objs",
    "export_hierarchy_flatten_bones",
    "export_use_gltfpack",
    "export_gpu_instances",
    "export_apply",
)


def _gltf_rna_identifiers():
    import bpy

    rna = bpy.ops.export_scene.gltf.get_rna_type()
    return {prop.identifier for prop in rna.properties}


def filter_export_kwargs(kwargs, identifiers, log=None):
    """Drop keys the current Blender operator does not know, and warn."""
    kept = {}
    dropped = []
    for key, value in kwargs.items():
        if key in identifiers or key == "filepath":
            kept[key] = value
        else:
            dropped.append(key)
    if dropped and log is not None:
        log(f"export preset dropped unsupported kwargs: {', '.join(dropped)}")
    return kept


def assert_not_forbidden(kwargs):
    bad = [key for key in FORBIDDEN_IF_TRUE if kwargs.get(key) is True]
    if bad:
        raise RuntimeError(
            "official GLB preset forbids flattening / gltfpack / instancing / apply-modifiers "
            f"on the default path; got true: {', '.join(bad)}"
        )


def official_kwargs(*, filepath, draco=False, extra=None):
    kwargs = dict(EXPORT_GLB_KWARGS)
    kwargs["filepath"] = filepath
    if draco:
        kwargs["export_draco_mesh_compression_enable"] = True
        kwargs["export_draco_mesh_compression_level"] = 6
    if extra:
        kwargs.update(extra)
    return kwargs


def export_glb(filepath, *, draco=False, extra=None, log=None):
    """Export the current Blender scene with the official preset."""
    import bpy

    kwargs = official_kwargs(filepath=filepath, draco=draco, extra=extra)
    kwargs = filter_export_kwargs(kwargs, _gltf_rna_identifiers(), log=log)
    assert_not_forbidden(kwargs)
    result = bpy.ops.export_scene.gltf(**kwargs)
    if result != {"FINISHED"}:
        raise RuntimeError(f"export_scene.gltf did not finish: {result}")
    return kwargs


def dump_scene_names(path):
    """Dump object / material / camera / pivot names from the current Blender scene."""
    import bpy

    objects = []
    for obj in bpy.data.objects:
        parent = obj.parent.name if obj.parent else None
        kind = obj.type
        extras = {}
        if "replace_id" in obj:
            extras["replace_id"] = obj["replace_id"]
        objects.append({
            "name": obj.name,
            "parent": parent,
            "kind": kind,
            "materials": [slot.material.name for slot in obj.material_slots if slot.material],
            "extras": extras or None,
        })
    materials = []
    for mat in bpy.data.materials:
        color = [1, 1, 1, 1]
        metallic = 0.0
        roughness = 0.5
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    if "Base Color" in node.inputs:
                        color = list(node.inputs["Base Color"].default_value)
                    if "Metallic" in node.inputs:
                        metallic = float(node.inputs["Metallic"].default_value)
                    if "Roughness" in node.inputs:
                        roughness = float(node.inputs["Roughness"].default_value)
                    break
        materials.append({
            "name": mat.name,
            "baseColorFactor": color,
            "metallic": metallic,
            "roughness": roughness,
        })
    payload = {
        "version": "mutracer-names/1",
        "source": "blender-scene",
        "nodes": objects,
        "materials": materials,
        "cameras": [obj.name for obj in bpy.data.objects if obj.type == "CAMERA"],
        "pivots": [obj.name for obj in bpy.data.objects if "pivot" in obj.name.lower()],
        "placeholders": [
            {"name": obj.name, "replace_id": obj["replace_id"]}
            for obj in bpy.data.objects if "replace_id" in obj
        ],
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


def _argv_after_dash():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return sys.argv[1:]


def _import_input(path, importer):
    import bpy

    path = str(path)
    kind = importer
    if kind == "auto":
        suffix = Path(path).suffix.lower()
        kind = {".fbx": "fbx", ".stl": "stl", ".glb": "glb", ".gltf": "gltf"}.get(suffix, "")
        if not kind:
            raise SystemExit(f"cannot infer importer for {path}")
    if kind == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif kind == "stl":
        bpy.ops.wm.stl_import(filepath=path)
    elif kind in {"glb", "gltf"}:
        bpy.ops.import_scene.gltf(filepath=path)
    elif kind == "none":
        return
    else:
        raise SystemExit(f"unknown importer: {kind}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Official MuTracer GLB export")
    parser.add_argument("--input", help="FBX / STL / GLB / glTF to import first")
    parser.add_argument("--output", required=True, help="Destination .glb")
    parser.add_argument("--importer", default="auto", choices=["auto", "fbx", "stl", "glb", "gltf", "none"])
    parser.add_argument("--dump-names", help="Write Blender-side name dump JSON before export")
    parser.add_argument("--draco", action="store_true", help="Allow Draco (names must still survive)")
    parser.add_argument("--factory-empty", action="store_true", default=True,
                        help="Start from an empty factory scene (default on)")
    args = parser.parse_args(argv if argv is not None else _argv_after_dash())

    import bpy

    if args.input and args.importer != "none":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _import_input(args.input, args.importer)
    elif args.importer == "none" and not args.input:
        pass
    elif not args.input:
        # Still useful when the .blend already has a scene.
        pass

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.dump_names:
        dump_scene_names(args.dump_names)
    export_glb(str(out), draco=args.draco, log=lambda msg: print(msg, file=sys.stderr))
    print(f"exported {out}")


if __name__ == "__main__":
    main()
