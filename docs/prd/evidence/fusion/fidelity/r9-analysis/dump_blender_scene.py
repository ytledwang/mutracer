#!/usr/bin/env python3
"""r9 diagnostic: dump world-space camera, mesh AABBs, projected bboxes, and light
positions as blender_inner currently applies them. Also compute the 'accumulate in
UE space, convert once' light positions for comparison. No path trace, no retune.
Does not import or modify blender_inner.py (it runs at import time).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

def arg(name, default=""):
    return argv[argv.index(name) + 1] if name in argv else default

def identity():
    return Matrix.Identity(4)

def swap_yz():
    return Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))

def gltf_to_ue():
    return Matrix((
        (0.0, 0.0, -1.0, 0.0),
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))

def sanitize(matrix):
    matrix = matrix.copy()
    matrix[3][0] = 0.0
    matrix[3][1] = 0.0
    matrix[3][2] = 0.0
    matrix[3][3] = 1.0
    return matrix

def blender_gltf_import_basis():
    return Matrix.Rotation(math.radians(90), 4, "X")

def mesh_basis_from_ue(ue_local):
    return sanitize(
        swap_yz()
        @ ue_local
        @ gltf_to_ue()
        @ blender_gltf_import_basis().inverted()
    )

def ue_basis_from_view():
    return Matrix((
        (0.0, 0.0, -1.0, 0.0),
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))

def ue_rotation(rotation_euler):
    roll = math.radians(rotation_euler[0])
    pitch = math.radians(rotation_euler[1])
    yaw = math.radians(rotation_euler[2])
    sr, cr = math.sin(roll), math.cos(roll)
    sp, cp = math.sin(pitch), math.cos(pitch)
    sy, cy = math.sin(yaw), math.cos(yaw)
    columns = (
        (cp * cy, cp * sy, sp),
        (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp),
        (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp),
    )
    return Matrix((
        (columns[0][0], columns[1][0], columns[2][0], 0.0),
        (columns[0][1], columns[1][1], columns[2][1], 0.0),
        (columns[0][2], columns[1][2], columns[2][2], 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))

def ue_local_matrix(entity, with_scale=True):
    if not entity:
        return identity()
    translation = entity.get("position") or [0.0, 0.0, 0.0]
    rotation = ue_rotation(entity.get("rotation_euler") or [0.0, 0.0, 0.0])
    scale = (entity.get("scale") or [1.0, 1.0, 1.0]) if with_scale else [1.0, 1.0, 1.0]
    for index in range(3):
        rotation[index][0] *= scale[0]
        rotation[index][1] *= scale[1]
        rotation[index][2] *= scale[2]
    rotation[0][3] = translation[0]
    rotation[1][3] = translation[1]
    rotation[2][3] = translation[2]
    return rotation

def camera_basis_from_ue(entity):
    return swap_yz() @ ue_local_matrix(entity, with_scale=False) @ ue_basis_from_view()

def light_basis_from_ue(entity):
    return sanitize(swap_yz() @ ue_local_matrix(entity) @ ue_basis_from_view())

def vlist(v):
    return [round(float(v[i]), 6) for i in range(3)]

def m4(m):
    return [[round(m[i][j], 6) for j in range(4)] for i in range(4)]

scene_path = arg("--scene")
assets_path = arg("--assets-file")
view_id = arg("--view")
out_json = arg("--out-json")
out_png = arg("--out-png")
width = int(arg("--width", "1920"))
height = int(arg("--height", "1080"))

with open(scene_path, encoding="utf-8") as f:
    raw = json.load(f)
stage_scene = raw.get("scene_json", raw)
with open(assets_path, encoding="utf-8") as f:
    assets = json.load(f)

bpy.ops.wm.read_factory_settings(use_empty=True)

# ---- import meshes the same way blender_inner does ----
mesh_records = []

def add_instance(mesh_id, transform, model_name, model_id):
    mesh = (stage_scene.get("meshes") or {}).get(mesh_id) or {}
    asset_url = mesh.get("url")
    asset_path = assets.get(asset_url)
    if not asset_path or not os.path.isfile(asset_path):
        mesh_records.append({"model": model_name, "model_id": model_id, "mesh": mesh.get("name"), "error": "missing_asset", "url": asset_url})
        return None
    previous = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=asset_path)
    imported = [obj for obj in bpy.context.selected_objects if obj not in previous]
    root = bpy.data.objects.new(f"inst_{mesh_id[:8]}", None)
    bpy.context.scene.collection.objects.link(root)
    world_matrices = [
        (obj, obj.matrix_world.copy())
        for obj in imported
        if obj.parent is None or obj.parent not in imported
    ]
    for imported_object, world_matrix in world_matrices:
        imported_object.parent = root
        imported_object.matrix_parent_inverse = Matrix.Identity(4)
        imported_object.matrix_world = world_matrix
    root.matrix_world = transform
    bpy.context.view_layer.update()
    # world bbox from evaluated mesh verts
    corners = []
    for obj in imported:
        if obj.type != "MESH" or obj.data is None:
            continue
        for vert in obj.data.vertices:
            corners.append(obj.matrix_world @ vert.co)
    if not corners:
        mesh_records.append({"model": model_name, "mesh": mesh.get("name"), "error": "no_verts"})
        return root
    xs = [c.x for c in corners]; ys = [c.y for c in corners]; zs = [c.z for c in corners]
    aabb = {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)],
            "span": [max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)]}
    thin = int(min(range(3), key=lambda i: aabb["span"][i]))
    mesh_records.append({
        "model": model_name,
        "model_id": model_id,
        "mesh": mesh.get("name"),
        "n_verts": sum(len(obj.data.vertices) for obj in imported if obj.type == "MESH"),
        "world_aabb": {k: [round(x, 6) for x in v] for k, v in aabb.items()},
        "thin_axis_blender": "XYZ"[thin],
        "thin_span": round(aabb["span"][thin], 6),
        "root_matrix": m4(root.matrix_world),
    })
    return root

def walk(node_id, parent_matrix):
    node = (stage_scene.get("models") or {}).get(node_id)
    if not node or node.get("is_visible") is False:
        return
    matrix = parent_matrix @ ue_local_matrix(node)
    if node.get("type") == "model" and node.get("mesh"):
        add_instance(node["mesh"], mesh_basis_from_ue(matrix), node.get("name"), node_id)
    for child in node.get("children", []) or []:
        walk(child, matrix)

for model_id, node in (stage_scene.get("models") or {}).items():
    if node.get("type") == "root":
        walk(model_id, identity())

# ---- lights: current (buggy parent compose) vs correct (UE-accumulate, convert once) ----
current_lights = []
correct_lights = []

def add_light_current(light_id, parent_matrix, depth):
    node = (stage_scene.get("lights") or {}).get(light_id)
    if not node or node.get("is_visible") is False:
        return
    matrix = parent_matrix @ light_basis_from_ue(node)
    if node.get("type") == "light":
        data = node.get("light") or {}
        loc = matrix.to_translation()
        # area light "forward" in Blender is -Z
        fwd = (matrix @ Vector((0, 0, -1, 0))).xyz.normalized() if matrix else Vector((0, 0, -1))
        current_lights.append({
            "name": node.get("name"),
            "id": light_id,
            "depth": depth,
            "type": data.get("type"),
            "power_raw": data.get("power"),
            "size_x": data.get("size_x"),
            "size_z": data.get("size_z"),
            "radius": data.get("radius"),
            "json_pos": node.get("position"),
            "json_rot": node.get("rotation_euler"),
            "applied_loc": vlist(loc),
            "applied_forward_minusZ": vlist(fwd),
        })
    for child in node.get("children", []) or []:
        add_light_current(child, matrix, depth + 1)

def add_light_correct(light_id, parent_ue, depth):
    node = (stage_scene.get("lights") or {}).get(light_id)
    if not node or node.get("is_visible") is False:
        return
    ue = parent_ue @ ue_local_matrix(node)
    if node.get("type") == "light":
        matrix = sanitize(swap_yz() @ ue @ ue_basis_from_view())
        data = node.get("light") or {}
        loc = matrix.to_translation()
        fwd = (matrix @ Vector((0, 0, -1, 0))).xyz.normalized()
        correct_lights.append({
            "name": node.get("name"),
            "id": light_id,
            "depth": depth,
            "type": data.get("type"),
            "power_raw": data.get("power"),
            "json_pos": node.get("position"),
            "correct_loc": vlist(loc),
            "correct_forward_minusZ": vlist(fwd),
        })
    for child in node.get("children", []) or []:
        add_light_correct(child, ue, depth + 1)

for light_id, node in (stage_scene.get("lights") or {}).items():
    if node.get("type") == "root":
        add_light_current(light_id, identity(), 0)
        add_light_correct(light_id, identity(), 0)

# ---- camera as blender_inner does (no parent chain) ----
views = stage_scene.get("views") or {}
view = views.get(view_id) or (next(iter(views.values())) if views else {})
camera_id = view.get("active_camera")
camera_data = (stage_scene.get("cameras") or {}).get(camera_id)
scene = bpy.context.scene
camera_info = {}
if camera_data:
    camera_camera = camera_data.get("camera", {})
    cam = bpy.data.cameras.new("camera")
    cam.sensor_width = camera_camera.get("sensor_width", 24.576)
    fov = math.radians(camera_camera.get("fov", 75))
    cam.sensor_fit = "HORIZONTAL"
    cam.lens = cam.sensor_width / (2 * math.tan(fov / 2))
    cam_obj = bpy.data.objects.new("camera", cam)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.matrix_world = camera_basis_from_ue(camera_data)
    scene.camera = cam_obj
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    bpy.context.view_layer.update()
    loc = cam_obj.matrix_world.to_translation()
    fwd = (cam_obj.matrix_world @ Vector((0, 0, -1, 0))).xyz.normalized()
    up = (cam_obj.matrix_world @ Vector((0, 1, 0, 0))).xyz.normalized()
    # Scene-up after swap_yz is Blender +Y (UE +Z)
    horiz = math.sqrt(fwd.x ** 2 + fwd.z ** 2)
    pitch_scene = math.degrees(math.atan2(fwd.y, horiz))
    camera_info = {
        "id": camera_id,
        "name": camera_data.get("name"),
        "json_pos": camera_data.get("position"),
        "json_rot_rpy_deg": camera_data.get("rotation_euler"),
        "fov_h_deg": camera_camera.get("fov"),
        "sensor_width": camera_camera.get("sensor_width"),
        "sensor_fit": "HORIZONTAL",
        "lens_mm": round(float(cam.lens), 4),
        "blender_loc": vlist(loc),
        "blender_forward_minusZ": vlist(fwd),
        "blender_up_plusY": vlist(up),
        "look_down_sceneYup_deg": round(-pitch_scene, 4),
        "parent_chain_applied": False,
        "note": "camera_basis_from_ue(entity) only; camera_root / group not multiplied",
    }

# ---- project mesh aabbs into the camera ----
from bpy_extras.object_utils import world_to_camera_view

def project_point(world):
    ndc = world_to_camera_view(scene, scene.camera, world)
    # ndc.x/y in 0-1 (y from bottom); convert to pixel y-down
    return [round(ndc.x * width, 2), round((1.0 - ndc.y) * height, 2), round(float(ndc.z), 4)]

# Recompute projected 2d bbox from all mesh verts
for rec, obj_root_name in zip([], []):
    pass

# Walk objects
projected = []
for rec in mesh_records:
    # find root by name inst_
    pass

# Collect from actual objects
for obj in list(bpy.context.scene.objects):
    if not obj.name.startswith("inst_"):
        continue
    # gather child mesh verts
    pts = []
    pix = []
    def collect(o):
        if o.type == "MESH" and o.data:
            for vert in o.data.vertices:
                w = o.matrix_world @ vert.co
                pts.append(w)
                pix.append(project_point(w))
        for ch in o.children:
            collect(ch)
    collect(obj)
    if not pix:
        continue
    xs = [p[0] for p in pix]; ys = [p[1] for p in pix]; zs = [p[2] for p in pix]
    # match rec by matrix / name
    projected.append({
        "root": obj.name,
        "n": len(pix),
        "pix_bbox": {"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys),
                     "w": max(xs)-min(xs), "h": max(ys)-min(ys)},
        "z_range": [min(zs), max(zs)],
        "behind_or_offscreen": bool(min(zs) < 0 or max(xs) < 0 or max(ys) < 0 or min(xs) > width or min(ys) > height),
    })

# union of all projected
if projected:
    ux0=min(p["pix_bbox"]["x0"] for p in projected)
    ux1=max(p["pix_bbox"]["x1"] for p in projected)
    uy0=min(p["pix_bbox"]["y0"] for p in projected)
    uy1=max(p["pix_bbox"]["y1"] for p in projected)
    union = {"x0": ux0, "x1": ux1, "y0": uy0, "y1": uy1, "w": ux1-ux0, "h": uy1-uy0,
             "width_frac": (ux1-ux0)/width, "height_frac": (uy1-uy0)/height}
else:
    union = None

# Combined world AABB
all_spans = {}
if mesh_records:
    mins = [min(r["world_aabb"]["min"][i] for r in mesh_records if "world_aabb" in r) for i in range(3)]
    maxs = [max(r["world_aabb"]["max"][i] for r in mesh_records if "world_aabb" in r) for i in range(3)]
    all_spans = {"min": [round(x,6) for x in mins], "max": [round(x,6) for x in maxs],
                 "span": [round(maxs[i]-mins[i],6) for i in range(3)]}
    thin = int(min(range(3), key=lambda i: all_spans["span"][i]))
    all_spans["thin_axis_blender"] = "XYZ"[thin]
    # If scene-up is Y, a horizontal hob is thin in Y
    all_spans["horizontal_if_thin_Y"] = all_spans["thin_axis_blender"] == "Y"
    all_spans["vertical_facing_camera_if_thin_Z"] = all_spans["thin_axis_blender"] == "Z"

# compare current vs correct lights
light_cmp = []
by_id_c = {l["id"]: l for l in correct_lights}
for cur in current_lights:
    cor = by_id_c.get(cur["id"])
    if not cor:
        continue
    d = [cur["applied_loc"][i] - cor["correct_loc"][i] for i in range(3)]
    dist = math.sqrt(sum(x*x for x in d))
    light_cmp.append({
        "name": cur["name"],
        "id": cur["id"],
        "depth": cur["depth"],
        "type": cur["type"],
        "power_raw": cur["power_raw"],
        "applied_loc": cur["applied_loc"],
        "correct_loc": cor["correct_loc"],
        "delta_applied_minus_correct": [round(x,6) for x in d],
        "delta_dist_m": round(dist, 6),
        "applied_forward": cur["applied_forward_minusZ"],
        "correct_forward": cor["correct_forward_minusZ"],
    })

# clay workbench render (geometry only, no path trace, no flag retune)
if out_png:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.45, 0.45, 0.48)
    scene.display.shading.show_shadows = True
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("w") if not scene.world else scene.world
    scene.world.color = (0.95, 0.95, 0.95)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out_png
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    bpy.ops.render.render(write_still=True)

result = {
    "task": "r9-analysis blender dump (no retune, workbench clay optional)",
    "view_id": view_id,
    "camera": camera_info,
    "product_world_aabb": all_spans,
    "meshes": mesh_records,
    "projected_union_px": union,
    "projected_per_root": projected,
    "lights_current_parent_compose": current_lights,
    "lights_correct_ue_accumulate": correct_lights,
    "lights_comparison": light_cmp,
    "conventions": {
        "scene_up_after_swap_yz": "Blender +Y (UE +Z)",
        "camera_look": "Blender local -Z",
        "current_light_path": "parent_matrix @ light_basis_from_ue(node) starting at identity from type=root; each root/group injects swap_yz @ ue_basis_from_view even if identity",
        "correct_light_path": "accumulate ue_local_matrix in UE space, convert once with swap_yz @ ue @ ue_basis_from_view (same pattern as walk() for models)",
        "camera_path": "camera_basis_from_ue(active camera) only; no parent chain",
        "mesh_path": "walk() accumulates ue_local then mesh_basis_from_ue once",
    },
}
os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print("[dump] wrote", out_json, "meshes", len(mesh_records), "lights", len(current_lights), "union", union)
if out_png:
    print("[dump] clay", out_png)
