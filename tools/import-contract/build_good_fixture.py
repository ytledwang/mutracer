#!/usr/bin/env python3
"""Build a small, commitable named-material + Pivot good fixture in Blender.

This is a synthetic fridge-like product, not the official kitchen shell
(RF_Kitchen_0302_Scene / ccdaa114-…), which is not on this machine. It is
also not Living Room. Local fridge poc-out meshes have no Pivot nodes, so
this script authors a compact contract fixture instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DEFAULT = HERE / "fixtures" / "good-named-pivot.glb"
# Synthetic placeholder id — do not pretend this is the official or M2 shell.
PLACEHOLDER_ID = "f1-named-pivot-placeholder"


def principled(name, color, *, metallic=0.0, roughness=0.4, transmission=0.0, alpha=1.0):
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    if "Base Color" in node.inputs:
        node.inputs["Base Color"].default_value = tuple(color)
    if "Metallic" in node.inputs:
        node.inputs["Metallic"].default_value = metallic
    if "Roughness" in node.inputs:
        node.inputs["Roughness"].default_value = roughness
    if transmission and "Transmission Weight" in node.inputs:
        node.inputs["Transmission Weight"].default_value = transmission
    elif transmission and "Transmission" in node.inputs:
        node.inputs["Transmission"].default_value = transmission
    if alpha < 1:
        mat.blend_method = "BLEND"
        if "Alpha" in node.inputs:
            node.inputs["Alpha"].default_value = alpha
    return mat


def mesh_cube(name, size, location, material, parent=None):
    import bpy

    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size if len(size) == 3 else (size, size, size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if obj.data:
        obj.data.name = name
    if material:
        obj.data.materials.clear()
        obj.data.materials.append(material)
    if parent is not None:
        obj.parent = parent
        # Keep the world location after parenting.
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
    return obj


def empty(name, location):
    import bpy

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=location)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def camera(name, location, look_at=(0, 0, 0.6)):
    import bpy
    from mathutils import Vector

    bpy.ops.object.camera_add(location=location)
    obj = bpy.context.active_object
    obj.name = name
    if obj.data:
        obj.data.name = name
    direction = Vector(look_at) - Vector(location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


def build(out: Path, names_path: Path):
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)

    white = principled("Fridge_White", (0.92, 0.93, 0.94, 1.0), roughness=0.35)
    plastic = principled("Crisper_Plastic", (0.15, 0.55, 0.62, 1.0), roughness=0.45)
    brass = principled("Handle_Brass", (0.78, 0.55, 0.22, 1.0), metallic=1.0, roughness=0.28)
    glass = principled("Fridge_Glass", (0.85, 0.93, 0.97, 0.3), roughness=0.05, transmission=0.8, alpha=0.35)

    body = mesh_cube("Fridge_Body", (0.7, 0.65, 1.4), (0, 0, 0.7), white)
    door_pivot = empty("Door_Pivot", (0.35, -0.33, 0.7))
    door = mesh_cube("Fridge_Door", (0.68, 0.08, 1.36), (0.0, -0.37, 0.7), white, parent=door_pivot)
    handle = mesh_cube("Fridge_Handle", (0.04, 0.04, 0.5), (0.28, -0.43, 0.7), brass, parent=door_pivot)
    crisper_pivot = empty("Crisper_Pivot", (0.0, 0.05, 0.22))
    crisper = mesh_cube("Crisper_Drawer", (0.55, 0.5, 0.2), (0.0, 0.05, 0.22), plastic, parent=crisper_pivot)
    shelf = mesh_cube("Fridge_Shelf", (0.55, 0.5, 0.02), (0.0, 0.0, 0.95), glass)

    placeholder = empty("Product_Slot", (0, 0, 0))
    placeholder["replace_id"] = PLACEHOLDER_ID
    # Some Blender versions need the property flagged as overridable / ID prop.
    placeholder.id_properties_ensure()

    camera("Cam_Front", (0.0, -2.6, 0.9), (0, 0, 0.7))
    camera("Cam_Close", (1.4, -1.6, 1.3), (0, 0, 0.8))

    # Door swing animation on the pivot, so flatten would break an animated ancestor.
    door_pivot.rotation_mode = "XYZ"
    door_pivot.rotation_euler = (0, 0, 0)
    door_pivot.keyframe_insert(data_path="rotation_euler", frame=1)
    door_pivot.rotation_euler[2] = 1.2
    door_pivot.keyframe_insert(data_path="rotation_euler", frame=40)
    if door_pivot.animation_data and door_pivot.animation_data.action:
        door_pivot.animation_data.action.name = "Door_Open"

    sys.path.insert(0, str(HERE))
    from export_glb_preset import dump_scene_names, export_glb

    names_path.parent.mkdir(parents=True, exist_ok=True)
    dump_scene_names(str(names_path))
    out.parent.mkdir(parents=True, exist_ok=True)
    export_glb(str(out), log=lambda msg: print(msg, file=sys.stderr))
    manifest = {
        "good": str(out),
        "source": "synthetic-named-pivot",
        "note": (
            "Synthetic fridge-like product authored for F1. Official kitchen shell "
            "RF_Kitchen_0302_Scene (ccdaa114-…) is not local and was not used. "
            "Living Room was not used. Local fridge poc-out GLBs had no Pivot nodes."
        ),
        "placeholder_id": PLACEHOLDER_ID,
        "expected_pivots": ["Door_Pivot", "Crisper_Pivot"],
        "expected_materials": ["Fridge_White", "Crisper_Plastic", "Handle_Brass", "Fridge_Glass"],
        "expected_cameras": ["Cam_Front", "Cam_Close"],
    }
    (HERE / "fixtures" / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    out = Path(argv[0]) if argv else OUT_DEFAULT
    names = Path(argv[1]) if len(argv) > 1 else HERE / "fixtures" / "names-source.json"
    build(out, names)


if __name__ == "__main__":
    main()
