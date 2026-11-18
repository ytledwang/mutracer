#!/usr/bin/env python3
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Euler, Matrix


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=""):
    return argv[argv.index(name) + 1] if name in argv else default


def load_assets():
    assets_path = arg("--assets-file")
    if assets_path:
        with open(assets_path, encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(arg("--assets", "{}"))


def load_scene(path):
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    # run_blender_final.py hands the wrapped cloud payload; the dual-track CLI
    # hands the bare snapshot.
    return raw.get("scene_json", raw)


scene_json_path = arg("--scene")
assets = load_assets()
view_id = arg("--view")
out_path = arg("--out", "/tmp/render.png")
spp = int(arg("--spp", "32"))
denoise = arg("--denoise", "1") == "1"
width_override = arg("--width")
height_override = arg("--height")
mask_out_path = arg("--mask-out")
# Tunables recorded in NOTES; defaults are the calibrated values.
AREA_LIGHT_ENERGY_PER_POWER = float(arg("--light-scale", "7.2"))
SKY_STRENGTH_SCALE = float(arg("--sky-scale", "0.28"))
HDRI_REFLECTION_SCALE = float(arg("--hdri-reflection", "0.12"))
EXPOSURE_BIAS_EV = float(arg("--exposure-bias", "0"))
DRAWER_PEARL_ALBEDO = float(arg("--drawer-albedo", "0.88"))
CHARCOAL_ALBEDO = float(arg("--charcoal-albedo", "0.015"))
EDGE_LEFT_ALBEDO = float(arg("--edge-left-albedo", "0.22"))
EDGE_LEFT_ROUGHNESS = float(arg("--edge-left-roughness", "0.4"))
EDGE_LEFT_METALNESS = float(arg("--edge-left-metalness", "0.3"))
EDGE_RIGHT_ALBEDO = float(arg("--edge-right-albedo", "0"))
EDGE_RIGHT_ROUGHNESS = float(arg("--edge-right-roughness", "0.45"))
EDGE_RIGHT_METALNESS = float(arg("--edge-right-metalness", "0"))
EDGE_LEFT_SPECULAR = float(arg("--edge-left-specular", "0.5"))
EDGE_RIGHT_SPECULAR = float(arg("--edge-right-specular", "0"))
INTERIOR_LIFT = float(arg("--interior-lift", "0.60"))
INTERIOR_LIFT_LOW = float(arg("--interior-lift-low", "0.30"))
INTERIOR_EMIT = float(arg("--interior-emit", "0.04"))
INTERIOR_EMIT_Z0 = float(arg("--interior-emit-z0", "1.25"))
INTERIOR_EMIT_Z1 = float(arg("--interior-emit-z1", "1.55"))
INTERIOR_SPLIT_Y = float(arg("--interior-split-y", "0.30"))
FLAKE_STRENGTH = float(arg("--flake", "0.15"))
FILL_SCALE = float(arg("--fill-scale", "0"))
# Opt-in only (defaults keep the Standard + display_post path byte-identical).
TONEMAP = arg("--tonemap", "none") or "none"
FALLBACK_LIGHT = (arg("--fallback-light", "1") or "1") == "1"
LINEAR_OUT = arg("--linear-out")
# "" = ignore hdri_angle (default, unchanged); "scene" = environment hdri_angle; else degrees.
HDRI_ANGLE = arg("--hdri-angle", "")
# r7 opt-ins: UE-faithful environment / material translation (absent = unchanged).
ENV_MODE = arg("--env-mode", "legacy") or "legacy"  # legacy | ue
SKYLIGHT_SCALE = float(arg("--skylight-scale", "1.0"))  # Cycles strength per UE SkyLight intensity unit
WHITE_SKY_SCALE = float(arg("--white-sky-scale", "0"))  # backdrop white leaking into non-camera rays
HDRI_MIRROR = (arg("--hdri-mirror", "0") or "0") == "1"
MATERIAL_MODE = arg("--material-mode", "legacy") or "legacy"  # legacy | stage
LIGHT_UNITS = arg("--light-units", "legacy") or "legacy"  # legacy | candela
if LIGHT_UNITS not in ("legacy", "candela"):
    raise ValueError(f"Unsupported --light-units {LIGHT_UNITS}")
DISPLAY_UNITS = arg("--display-units", "legacy") or "legacy"  # legacy | engine (r12: UE 5.5.4 source-verified display scale)
if DISPLAY_UNITS not in ("legacy", "engine"):
    raise ValueError(f"Unsupported --display-units {DISPLAY_UNITS}")
GLASS_MODE = arg("--glass-mode", "solid") or "solid"  # stage only: solid | thin (UE thin-translucent guess)
if ENV_MODE not in ("legacy", "ue") or MATERIAL_MODE not in ("legacy", "stage"):
    raise ValueError(f"Unsupported --env-mode {ENV_MODE} / --material-mode {MATERIAL_MODE}")
if TONEMAP not in ("none", "ue-filmic", "ue55"):
    raise ValueError(f"Unsupported --tonemap {TONEMAP}")

stage_scene = load_scene(scene_json_path)

# Blender keeps the factory cube until the scene is reset; it would render over
# the whole stage and poison the silhouette.
bpy.ops.wm.read_factory_settings(use_empty=True)


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
    # Stage render default glTF->UE map, UE = (-z, x, y).
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
    # Blender's glTF importer bakes glTF Y-up vertices into Blender Z-up.
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


def light_world_from_ue(ue_local):
    return sanitize(swap_yz() @ ue_local @ ue_basis_from_view())


def light_basis_from_ue(entity):
    return light_world_from_ue(ue_local_matrix(entity))


def add_instance(mesh_id, transform):
    mesh = (stage_scene.get("meshes") or {}).get(mesh_id) or {}
    asset_url = mesh.get("url")
    asset_path = assets.get(asset_url)
    if not asset_path or not os.path.isfile(asset_path):
        print(f"[asset] missing {asset_url}", flush=True)
        return None
    previous = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=asset_path)
    # Selection is not reliable for "what this import created": earlier objects
    # stay selected, so filter against the objects that existed before.
    imported = [obj for obj in bpy.context.selected_objects if obj not in previous]
    root = bpy.data.objects.new(f"inst_{mesh_id[:8]}", None)
    bpy.context.scene.collection.objects.link(root)
    # Blender parents by fitting matrix_parent_inverse to the child's current world
    # matrix, so assigning root.matrix_world afterwards would stack the offset twice.
    # Zero the inverse, then place the child in world space.
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
    current_instance["side"] = instance_side(imported)
    if os.environ.get("DUAL_TRACK_DEBUG_INSTANCES"):
        print("[inst]", (stage_scene.get("meshes") or {}).get(mesh_id, {}).get("name"),
              round(current_instance["side"], 3), round(current_instance["height"], 3), flush=True)
    assign_stage_materials(mesh_id, imported)
    return root


stage_material_cache = {}
current_instance = {"side": 0.0, "height": 0.0}


def early_camera_matrix():
    views = stage_scene.get("views") or {}
    first_view = views.get(view_id) or (next(iter(views.values())) if views else {})
    cameras = stage_scene.get("cameras") or {}
    entity = cameras.get(first_view.get("active_camera")) or next(
        (c for c in cameras.values() if c.get("type") == "camera"), None
    )
    return camera_basis_from_ue(entity).inverted() if entity else Matrix.Identity(4)


def instance_side(imported):
    # Camera-space x of the imported geometry's bounding-box centre: <0 left, >0 right.
    from mathutils import Vector

    low = Vector((1e9, 1e9, 1e9))
    high = Vector((-1e9, -1e9, -1e9))
    for obj in imported:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = early_camera_inverse @ (obj.matrix_world @ Vector(corner))
            low = Vector(min(a, b) for a, b in zip(low, point))
            high = Vector(max(a, b) for a, b in zip(high, point))
    current_instance["height"] = (low.y + high.y) / 2.0
    return (low.x + high.x) / 2.0


early_camera_inverse = early_camera_matrix()


def is_cad_debug_name(name):
    return (
        name.startswith("solid_")
        or (3 <= len(name) <= 8 and all(character in "0123456789abcdefABCDEF" for character in name))
        or (bool(name) and all(character.isdigit() for character in name))
    )


def material_override(material_id, mesh_id):
    side = current_instance["side"]
    cache_key = (material_id, mesh_id, side < 0, current_instance["height"] > INTERIOR_SPLIT_Y)
    if cache_key in stage_material_cache:
        return stage_material_cache[cache_key]
    material = (stage_scene.get("materials") or {}).get(material_id) or {}
    name = material.get("name", "")
    if MATERIAL_MODE == "stage":
        override = stage_faithful_override(material)
        stage_material_cache[cache_key] = override
        return override
    master = material.get("master", "")
    color = list(material.get("base_color_rgb") or [0.8, 0.8, 0.8])
    mesh_name = ((stage_scene.get("meshes") or {}).get(mesh_id) or {}).get("name", "")
    is_glass = "Glass" in master
    glass_roughness = material.get("glass_roughness_scalar")
    if is_glass and glass_roughness is not None:
        roughness = max(0.0, min(1.0, float(glass_roughness)))
    elif material.get("roughness_scalar") is not None:
        roughness = max(0.0, min(1.0, float(material.get("roughness_scalar", 0.5))))
    elif master.startswith("Haier_CMF") and material.get("roughness_min_scalar") is None and material.get("roughness_max_scalar") is None:
        roughness = 0.35
    else:
        roughness = max(0.0, min(1.0, (
            float(material.get("roughness_min_scalar", 0.5))
            + float(material.get("roughness_max_scalar", 0.5))
        ) / 2))
    metalness = (
        max(0.0, min(1.0, float(material.get("metallic_scalar", 0.0))))
        if material.get("metallic_scalar") is not None
        else (0.85 if "Metal" in master else 0.0)
    )
    if is_cad_debug_name(name):
        chroma = max(color) - min(color)
        if chroma > 0.35:
            color = [0.97, 0.97, 0.97]
        roughness = 0.45
        metalness = 0.0
        master = "Plastic"
    frosted = "Frosted" in name or "Frosted" in master
    if is_glass and not frosted:
        roughness = min(roughness, 0.1)
    elif is_glass:
        roughness = max(roughness, 0.3)
    lacquer = False
    if master.startswith("Haier_CMF"):
        luminance = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
        drawer_face = mesh_name.startswith("门体-") and (
            "星蕴银" in name
            or "矿石银" in name
            or "珍珠米" in name
            or 0.25 <= luminance < 0.75
        )
        if drawer_face:
            color = [DRAWER_PEARL_ALBEDO, DRAWER_PEARL_ALBEDO, DRAWER_PEARL_ALBEDO * 0.995]
            metalness = 0.02
            roughness = 0.35
        elif luminance < 0.35:
            roughness = max(roughness, 0.25)
        lacquer = True
        if luminance >= 0.5:
            metalness = min(metalness, 0.3)
    door_edge_meshes = {
        "门体-51_Default", "门体-52_Default", "门体-53_Default", "门体-58_Default",
        "门体-62_Default", "门体-64_Default", "门体-76_Default", "门体-79_Default",
    }
    is_charcoal = False
    specular = 0.5
    if "钣金喷粉" in name:
        color = [CHARCOAL_ALBEDO, CHARCOAL_ALBEDO, CHARCOAL_ALBEDO * 1.1]
        roughness = 0.45
        metalness = 0.12
        is_charcoal = True
    if mesh_name in door_edge_meshes and (
        "钣金喷粉" in name or "Plastic_Coated" in name or "Plastic_Rough" in name or name == "11"
    ):
        albedo, roughness, metalness, specular = (
            (EDGE_LEFT_ALBEDO, EDGE_LEFT_ROUGHNESS, EDGE_LEFT_METALNESS, EDGE_LEFT_SPECULAR)
            if side < 0
            else (EDGE_RIGHT_ALBEDO, EDGE_RIGHT_ROUGHNESS, EDGE_RIGHT_METALNESS, EDGE_RIGHT_SPECULAR)
        )
        color = [albedo, albedo, albedo * 1.1]
        is_charcoal = True
    if is_charcoal:
        lacquer = False
    lift = INTERIOR_LIFT if current_instance["height"] > INTERIOR_SPLIT_Y else INTERIOR_LIFT_LOW
    interior = (
        lift > 0.0
        and not is_charcoal
        and not is_glass
        and not master.startswith("Haier_CMF")
        and mesh_name not in door_edge_meshes
    )
    emit = 0.0
    if interior:
        color = [min(1.0, c + lift * (1.0 - c)) for c in color]
        if current_instance["height"] > INTERIOR_SPLIT_Y:
            emit = INTERIOR_EMIT
    textures = {}
    for field, key in (("basecolor_tex", "basecolor"), ("normal_tex", "normal"), ("roughness_tex", "roughness")):
        texture_id = material.get(field)
        if texture_id:
            texture = (stage_scene.get("textures") or {}).get(texture_id) or {}
            texture_url = texture.get("urls") or texture.get("url")
            texture_path = assets.get(texture_url)
            if texture_path and os.path.isfile(texture_path):
                textures[key] = texture_path
    override = {
        "name": name,
        "color": color,
        "roughness": roughness,
        "metalness": metalness,
        "glass": "Glass" in master,
        "lacquer": lacquer,
        "specular": specular,
        "emit": emit,
        "flake": lacquer and FLAKE_STRENGTH > 0.0,
        "roughness_floor": 0.45 if is_charcoal else 0.0,
        "basecolor_path": textures.get("basecolor"),
        "normal_path": textures.get("normal"),
        "roughness_path": textures.get("roughness"),
    }
    stage_material_cache[cache_key] = override
    return override


def stage_faithful_override(material):
    # r7: scene JSON values as-is (UE master parameters), no fridge-specific hacks.
    master = material.get("master", "")
    is_glass = "Glass" in master
    if is_glass and material.get("glass_roughness_scalar") is not None:
        roughness = float(material["glass_roughness_scalar"])
    elif material.get("roughness_scalar") is not None:
        roughness = float(material["roughness_scalar"])
    elif material.get("roughness_min_scalar") is not None or material.get("roughness_max_scalar") is not None:
        roughness = (float(material.get("roughness_min_scalar", 0.5)) + float(material.get("roughness_max_scalar", 0.5))) / 2
    else:
        roughness = 0.5
    if material.get("metallic_scalar") is not None:
        metalness = float(material["metallic_scalar"])
    else:
        metalness = 1.0 if "Metal" in master else 0.0
    coat = material.get("clear_coat_scalar", material.get("clear_coat_amount_scalar", 0.0))
    color = list(material.get("transmission_color_rgb") or material.get("base_color_rgb") or [0.8, 0.8, 0.8]) if is_glass else list(material.get("base_color_rgb") or [0.8, 0.8, 0.8])
    textures = {}
    for field, key in (("basecolor_tex", "basecolor"), ("normal_tex", "normal"), ("roughness_tex", "roughness")):
        texture_id = material.get(field)
        if texture_id:
            texture = (stage_scene.get("textures") or {}).get(texture_id) or {}
            texture_path = assets.get(texture.get("urls") or texture.get("url"))
            if texture_path and os.path.isfile(texture_path):
                textures[key] = texture_path
    return {
        "name": material.get("name", ""), "color": color,
        "roughness": max(0.0, min(1.0, roughness)), "metalness": max(0.0, min(1.0, metalness)),
        "glass": is_glass, "lacquer": False, "specular": float(material.get("specular_scalar", 0.5)),
        "emit": 0.0, "flake": False, "roughness_floor": 0.0,
        "basecolor_path": textures.get("basecolor"), "normal_path": textures.get("normal"),
        "roughness_path": textures.get("roughness"),
        "stage": {
            "coat": max(0.0, min(1.0, float(coat or 0.0))),
            "coat_roughness": float(material.get("clear_coat_roughness_scalar", 0.0)),
            "ior": float(material.get("ior_scalar", 1.45)) if is_glass else None,
            "emission": float(material.get("facing_intensity_scalar", 1.0)) if "Emissive" in master else 0.0,
        },
    }


def blender_material(override):
    name = override["name"]
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    node_tree = material.node_tree
    bsdf = node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*override["color"], 1.0)
    bsdf.inputs["Roughness"].default_value = override["roughness"]
    bsdf.inputs["Metallic"].default_value = override["metalness"]
    if override["emit"] > 0.0:
        bsdf.inputs["Emission Color"].default_value = (*override["color"], 1.0)
        # Strength ramps with world height so the cavity fades toward the lower shelves.
        geometry = node_tree.nodes.new("ShaderNodeNewGeometry")
        separate = node_tree.nodes.new("ShaderNodeSeparateXYZ")
        node_tree.links.new(geometry.outputs["Position"], separate.inputs["Vector"])
        ramp = node_tree.nodes.new("ShaderNodeMapRange")
        ramp.clamp = True
        ramp.inputs["From Min"].default_value = INTERIOR_EMIT_Z0
        ramp.inputs["From Max"].default_value = INTERIOR_EMIT_Z1
        ramp.inputs["To Min"].default_value = 0.0
        ramp.inputs["To Max"].default_value = override["emit"]
        node_tree.links.new(separate.outputs["Z"], ramp.inputs["Value"])
        node_tree.links.new(ramp.outputs["Result"], bsdf.inputs["Emission Strength"])
    bsdf.inputs["Specular IOR Level"].default_value = override["specular"]
    if override["glass"]:
        bsdf.inputs["Transmission Weight"].default_value = 0.9
        bsdf.inputs["IOR"].default_value = 1.45
    if override["lacquer"]:
        bsdf.inputs["Coat Weight"].default_value = 0.8
        bsdf.inputs["Coat Roughness"].default_value = 0.1
    if override["flake"]:
        # Fine voronoi flakes: cell-hash noise nudges metallic and coat roughness.
        coordinates = node_tree.nodes.new("ShaderNodeTexCoord")
        flake_noise = node_tree.nodes.new("ShaderNodeTexNoise")
        flake_noise.inputs["Scale"].default_value = 900.0
        flake_noise.inputs["Detail"].default_value = 0.0
        flake_noise.inputs["Roughness"].default_value = 1.0
        node_tree.links.new(coordinates.outputs["Object"], flake_noise.inputs["Vector"])
        centered = node_tree.nodes.new("ShaderNodeMath")
        centered.operation = "SUBTRACT"
        centered.inputs[1].default_value = 0.5
        node_tree.links.new(flake_noise.outputs["Fac"], centered.inputs[0])
        metallic_delta = node_tree.nodes.new("ShaderNodeMath")
        metallic_delta.operation = "MULTIPLY_ADD"
        metallic_delta.inputs[1].default_value = FLAKE_STRENGTH * 0.6
        metallic_delta.inputs[2].default_value = override["metalness"]
        node_tree.links.new(centered.outputs["Value"], metallic_delta.inputs[0])
        metallic_clamp = node_tree.nodes.new("ShaderNodeClamp")
        node_tree.links.new(metallic_delta.outputs["Value"], metallic_clamp.inputs["Value"])
        node_tree.links.new(metallic_clamp.outputs["Result"], bsdf.inputs["Metallic"])
        coat_delta = node_tree.nodes.new("ShaderNodeMath")
        coat_delta.operation = "MULTIPLY_ADD"
        coat_delta.inputs[1].default_value = FLAKE_STRENGTH * 0.3
        coat_delta.inputs[2].default_value = 0.1
        node_tree.links.new(centered.outputs["Value"], coat_delta.inputs[0])
        coat_clamp = node_tree.nodes.new("ShaderNodeClamp")
        node_tree.links.new(coat_delta.outputs["Value"], coat_clamp.inputs["Value"])
        node_tree.links.new(coat_clamp.outputs["Result"], bsdf.inputs["Coat Roughness"])
    stage = override.get("stage")
    if stage:
        bsdf.inputs["Coat Weight"].default_value = stage["coat"]
        bsdf.inputs["Coat Roughness"].default_value = stage["coat_roughness"]
        if stage["ior"] is not None:
            bsdf.inputs["Transmission Weight"].default_value = 1.0
            bsdf.inputs["IOR"].default_value = stage["ior"]
        if stage["ior"] is not None and GLASS_MODE == "thin":
            output = node_tree.nodes["Material Output"]
            transparent = node_tree.nodes.new("ShaderNodeBsdfTransparent")
            transparent.inputs["Color"].default_value = (*override["color"], 1.0)
            glossy = node_tree.nodes.new("ShaderNodeBsdfGlossy")
            glossy.inputs["Roughness"].default_value = override["roughness"]
            fresnel = node_tree.nodes.new("ShaderNodeFresnel")
            fresnel.inputs["IOR"].default_value = stage["ior"]
            thin_mix = node_tree.nodes.new("ShaderNodeMixShader")
            node_tree.links.new(fresnel.outputs["Fac"], thin_mix.inputs["Fac"])
            node_tree.links.new(transparent.outputs["BSDF"], thin_mix.inputs[1])
            node_tree.links.new(glossy.outputs["BSDF"], thin_mix.inputs[2])
            node_tree.links.new(thin_mix.outputs["Shader"], output.inputs["Surface"])
        if stage["emission"] > 0.0:
            bsdf.inputs["Emission Color"].default_value = (*override["color"], 1.0)
            # Engine mode rescales emission by 1/(683*ENGINE_DISPLAY_GRAY*1.2)
            # so the displayed result stays on the same unit lock as the sky.
            from ue_filmic import ENGINE_DISPLAY_GRAY
            emission_scale = 1.0 if DISPLAY_UNITS == "legacy" else 1.0 / (683.0 * ENGINE_DISPLAY_GRAY * 1.2)
            bsdf.inputs["Emission Strength"].default_value = stage["emission"] * emission_scale
    for texture_kind in ("basecolor", "normal", "roughness"):
        path = override.get(f"{texture_kind}_path")
        if not path:
            continue
        image = bpy.data.images.load(path)
        if texture_kind != "basecolor":
            image.colorspace_settings.name = "Non-Color"
        texture_node = node_tree.nodes.new("ShaderNodeTexImage")
        texture_node.image = image
        if texture_kind == "basecolor":
            node_tree.links.new(texture_node.outputs["Color"], bsdf.inputs["Base Color"])
        elif texture_kind == "normal":
            normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
            normal_map.inputs["Strength"].default_value = 1.0
            node_tree.links.new(texture_node.outputs["Color"], normal_map.inputs["Color"])
            node_tree.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        else:
            roughness_floor = override["roughness_floor"]
            if roughness_floor > 0.0:
                roughness_minimum = node_tree.nodes.new("ShaderNodeMath")
                roughness_minimum.operation = "MAXIMUM"
                roughness_minimum.inputs[1].default_value = roughness_floor
                roughness_minimum.inputs[2].default_value = 0.0
                node_tree.links.new(texture_node.outputs["Color"], roughness_minimum.inputs[0])
                node_tree.links.new(roughness_minimum.outputs["Value"], bsdf.inputs["Roughness"])
            else:
                node_tree.links.new(texture_node.outputs["Color"], bsdf.inputs["Roughness"])
    return material


def assign_stage_materials(mesh_id, imported):
    mesh = (stage_scene.get("meshes") or {}).get(mesh_id) or {}
    material_ids = mesh.get("materials") or []
    if not material_ids:
        return
    overrides = [material_override(material_id, mesh_id) for material_id in material_ids]
    materials = [blender_material(override) for override in overrides]
    for imported_object in imported:
        if imported_object.type != "MESH":
            continue
        if not imported_object.material_slots:
            imported_object.data.materials.append(None)
        for slot_index, slot in enumerate(imported_object.material_slots):
            slot.material = materials[min(slot_index, len(materials) - 1)]


def walk(node_id, parent_matrix):
    node = (stage_scene.get("models") or {}).get(node_id)
    if not node or node.get("is_visible") is False:
        return
    matrix = parent_matrix @ ue_local_matrix(node)
    if node.get("type") == "model" and node.get("mesh"):
        add_instance(node["mesh"], mesh_basis_from_ue(matrix))
    for child in node.get("children", []) or []:
        walk(child, matrix)


has_stage_light = False


def add_light(light_id, parent_matrix, visited):
    node = (stage_scene.get("lights") or {}).get(light_id)
    if not node or light_id in visited or node.get("is_visible") is False:
        return
    visited.add(light_id)
    # Accumulate in UE space, convert once — same algorithm as walk() for meshes.
    # Do not call light_basis_from_ue at every root/group: that injects an extra
    # swap_yz @ ue_basis_from_view even when the parent transform is identity.
    matrix_ue = parent_matrix @ ue_local_matrix(node)
    if node.get("type") == "light":
        matrix = light_world_from_ue(matrix_ue)
        data = node.get("light") or {}
        light_type = data.get("type")
        color = data.get("color") or [1.0, 1.0, 1.0]
        power = float(data.get("power", 0.0))
        if LIGHT_UNITS == "candela":
            # UE SpawnLight: IntensityUnits = Candelas, SetIntensity(power).
            # Cycles area/point energy is Watts. Photometric conversion uses 683 lm/W
            # (CIE 555 nm). UE 5.5.4 engine source (verified, not fitted):
            #   RectLight radiance nits = 2*I/A_m2  [RectLightComponent.cpp:174,313]
            #   => Lambertian area flux = 2*pi * I ; isotropic point/spot = 4*pi * I.
            # Sun/directional left as lux~W/m^2.
            if light_type == "area_light":
                energy = power * 2.0 * math.pi / 683.0
            elif light_type in ("point_light", "spot_light"):
                energy = power * 4.0 * math.pi / 683.0
            else:
                energy = power
        else:
            energy = power * AREA_LIGHT_ENERGY_PER_POWER
        if light_type == "area_light":
            light = bpy.data.lights.new(light_id[:8], type="AREA")
            light.shape = "RECTANGLE"
            light.size = float(data.get("size_x", 0.0)) / 100.0
            light.size_y = float(data.get("size_z", 0.0)) / 100.0
        elif light_type == "point_light":
            light = bpy.data.lights.new(light_id[:8], type="POINT")
            light.shadow_soft_size = max(0.01, float(data.get("radius", 0.0)) / 100.0)
        elif light_type == "directional_light":
            light = bpy.data.lights.new(light_id[:8], type="SUN")
        elif light_type == "spot_light":
            light = bpy.data.lights.new(light_id[:8], type="SPOT")
            light.spot_size = math.radians(max(0.1, min(89.9, float(data.get("spot_size", 45.0)))))
            light.spot_blend = max(0.0, min(1.0, float(data.get("blend", 0.0))))
        else:
            raise ValueError(f"Unsupported light type {light_type}")
        light.color = color
        light.energy = energy
        light_object = bpy.data.objects.new(light_id[:8], light)
        bpy.context.scene.collection.objects.link(light_object)
        light_object.matrix_world = matrix
        global has_stage_light
        has_stage_light = True
    for child in node.get("children", []) or []:
        add_light(child, matrix_ue, visited)


for model_id, node in (stage_scene.get("models") or {}).items():
    if node.get("type") == "root":
        walk(model_id, identity())

for light_id, node in (stage_scene.get("lights") or {}).items():
    if node.get("type") == "root":
        add_light(light_id, identity(), set())

if not has_stage_light and FALLBACK_LIGHT:
    fallback_position = Matrix.Translation((-0.04, -4.50, 2.30))
    fallback_direction = (-fallback_position.to_translation()).normalized()
    fallback_light = bpy.data.lights.new("soft_fill", type="AREA")
    fallback_light.energy = 200.0
    fallback_light.shape = "RECTANGLE"
    fallback_light.size = 1.5
    fallback_light.size_y = 1.0
    fallback_object = bpy.data.objects.new("soft_fill", fallback_light)
    bpy.context.scene.collection.objects.link(fallback_object)
    fallback_object.matrix_world = (
        fallback_position
        @ fallback_direction.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    )

if FILL_SCALE > 0.0:
    # Weak symmetric fill: two large soft panels left/right of the camera axis.
    for fill_x in (-1.8, 1.8):
        fill = bpy.data.lights.new(f"fill_{fill_x}", type="AREA")
        fill.shape = "RECTANGLE"
        fill.size = 2.0
        fill.size_y = 3.0
        fill.energy = FILL_SCALE
        fill_object = bpy.data.objects.new(f"fill_{fill_x}", fill)
        bpy.context.scene.collection.objects.link(fill_object)
        fill_position = Matrix.Translation((fill_x, -4.0, 1.0))
        fill_direction = (Matrix.Translation((0.0, 0.0, 1.0)).to_translation() - fill_position.to_translation()).normalized()
        fill_object.matrix_world = fill_position @ fill_direction.to_track_quat("-Z", "Y").to_matrix().to_4x4()

views = stage_scene.get("views") or {}
view = views.get(view_id) or (next(iter(views.values())) if views else {})

camera_id = view.get("active_camera")
camera_data = (stage_scene.get("cameras") or {}).get(camera_id)
if not camera_data:
    camera_data = next(
        (
            camera
            for camera in (stage_scene.get("cameras") or {}).values()
            if camera.get("type") == "camera"
        ),
        None,
    )

scene = bpy.context.scene
if camera_data:
    camera_camera = camera_data.get("camera", {})
    frame_size = camera_data.get("frame_size", [1920, 1080])
    render_width = int(width_override or frame_size[0])
    render_height = int(height_override or frame_size[1])
    camera = bpy.data.cameras.new("camera")
    camera.sensor_width = camera_camera.get("sensor_width", 24.576)
    fov = math.radians(camera_camera.get("fov", 75))
    camera.sensor_fit = "HORIZONTAL"
    camera.lens = camera.sensor_width / (2 * math.tan(fov / 2))
    camera_object = bpy.data.objects.new("camera", camera)
    bpy.context.scene.collection.objects.link(camera_object)
    camera_object.matrix_world = camera_basis_from_ue(camera_data)
    scene.camera = camera_object
    scene.render.resolution_x = render_width
    scene.render.resolution_y = render_height

environment_id = view.get("active_environment")
environment = (stage_scene.get("environments") or {}).get(environment_id)
environment_texture_path = None
environment_settings = (environment or {}).get("settings") or {}
background_type = environment_settings.get("background_type", "white")
texture_id = environment_settings.get("image")
texture = (stage_scene.get("textures") or {}).get(texture_id)
texture_url = texture and (texture.get("urls") or texture.get("url"))
environment_texture_path = assets.get(texture_url)

scene.render.film_transparent = False
view_transform = arg("--view-transform", "Standard") or "Standard"
scene.view_settings.view_transform = view_transform
print(f"[color] view_transform={view_transform}", flush=True)
world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
world_nodes = world.node_tree.nodes
world_links = world.node_tree.links
background = world_nodes["Background"]
world_output = world_nodes["World Output"]


def world_background(color, strength):
    node = world_nodes.new("ShaderNodeBackground")
    node.inputs["Color"].default_value = (*color, 1.0)
    node.inputs["Strength"].default_value = strength
    return node


def load_environment_node():
    node = world_nodes.new("ShaderNodeTexEnvironment")
    node.image = bpy.data.images.load(environment_texture_path)
    if HDRI_ANGLE:
        degrees = float(environment_settings.get("hdri_angle", 0.0)) if HDRI_ANGLE == "scene" else float(HDRI_ANGLE)
        coordinates = world_nodes.new("ShaderNodeTexCoord")
        mapping = world_nodes.new("ShaderNodeMapping")
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(degrees))
        if HDRI_MIRROR:
            mapping.inputs["Scale"].default_value = (1.0, -1.0, 1.0)
        world_links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
        world_links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        print(f"[env] hdri rotation z={degrees}", flush=True)
    return node


hdri_available = bool(environment_texture_path and os.path.isfile(environment_texture_path))
hdri_brightness = float(environment_settings.get("hdri_brightness", 1))
skylight_intensity = float(environment_settings.get("skylight_intensity", 0.35))
if ENV_MODE == "ue":
    # r7/r8 UE 1.0 mapping: lighting rays always see SkyLight = env EXR * skylight * k.
    # Camera rays follow the task background_type: white skybox (composited in ue55 post
    # via alpha, x HDRI_Brightness) or the env EXR x hdri_brightness.
    add_shader = world_nodes.new("ShaderNodeAddShader")
    sky_white = world_background((1.0, 1.0, 1.0), WHITE_SKY_SCALE * hdri_brightness)
    world_links.new(sky_white.outputs["Background"], add_shader.inputs[0])
    skylight = world_background((1.0, 1.0, 1.0), skylight_intensity * SKYLIGHT_SCALE)
    if hdri_available:
        environment_texture = load_environment_node()
        world_links.new(environment_texture.outputs["Color"], skylight.inputs["Color"])
    world_links.new(skylight.outputs["Background"], add_shader.inputs[1])
    if background_type == "white":
        camera_bg = world_background((1.0, 1.0, 1.0), 1.0)
    else:
        camera_bg = world_background((1.0, 1.0, 1.0), hdri_brightness)
        if hdri_available:
            if "environment_texture" not in locals():
                environment_texture = load_environment_node()
            world_links.new(environment_texture.outputs["Color"], camera_bg.inputs["Color"])
    light_path = world_nodes.new("ShaderNodeLightPath")
    mix = world_nodes.new("ShaderNodeMixShader")
    world_links.new(light_path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    world_links.new(add_shader.outputs["Shader"], mix.inputs[1])
    world_links.new(camera_bg.outputs["Background"], mix.inputs[2])
    world_links.new(mix.outputs["Shader"], world_output.inputs["Surface"])
    print(f"[env] ue bg={background_type} skylight={skylight_intensity}*{SKYLIGHT_SCALE} white_sky={WHITE_SKY_SCALE}*{hdri_brightness} cam_strength={1.0 if background_type=='white' else hdri_brightness} mirror={HDRI_MIRROR} lights={LIGHT_UNITS} display={DISPLAY_UNITS}", flush=True)
elif background_type == "white":
    # Camera rays see the pure white backdrop at full strength; every other ray
    # sees a dim skylight plus a faint HDRI, so the white backdrop does not
    # flood the scene with 1.0 radiance and blow out the body.
    camera_white = world_background((1.0, 1.0, 1.0), 1.0)
    sky = world_background((1.0, 1.0, 1.0), skylight_intensity * SKY_STRENGTH_SCALE)
    add_shader = world_nodes.new("ShaderNodeAddShader")
    world_links.new(sky.outputs["Background"], add_shader.inputs[0])
    if hdri_available and HDRI_REFLECTION_SCALE > 0.0:
        environment_texture = load_environment_node()
        reflection = world_background(
            (1.0, 1.0, 1.0), hdri_brightness * HDRI_REFLECTION_SCALE
        )
        world_links.new(environment_texture.outputs["Color"], reflection.inputs["Color"])
        world_links.new(reflection.outputs["Background"], add_shader.inputs[1])
    light_path = world_nodes.new("ShaderNodeLightPath")
    mix = world_nodes.new("ShaderNodeMixShader")
    world_links.new(light_path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    world_links.new(add_shader.outputs["Shader"], mix.inputs[1])
    world_links.new(camera_white.outputs["Background"], mix.inputs[2])
    world_links.new(mix.outputs["Shader"], world_output.inputs["Surface"])
elif hdri_available:
    environment_texture = load_environment_node()
    world_links.new(environment_texture.outputs["Color"], background.inputs["Color"])
    background.inputs["Strength"].default_value = min(hdri_brightness, 10.0)
else:
    background.inputs["Color"].default_value = (0.95, 0.95, 0.95, 1)
    background.inputs["Strength"].default_value = 1.0

post = ((camera_data or {}).get("camera") or {}).get("post_processing_settings") or {}
# UE: post.exposure -> AutoExposureBias (stops, 1:1). Blender: view_settings.exposure.
# EXPOSURE_BIAS_EV defaults to 0; radiometric gaps are tuned with light/sky scales.
scene.view_settings.exposure = float(post.get("exposure", 0.0)) + EXPOSURE_BIAS_EV

scene.render.engine = "CYCLES"
preferences = bpy.context.preferences.addons["cycles"].preferences
preferred_devices = ("METAL", "OPTIX", "CUDA") if sys.platform == "darwin" else (
    "OPTIX",
    "CUDA",
)
for device_type in preferred_devices:
    try:
        preferences.compute_device_type = device_type
        preferences.get_devices()
        gpu_count = 0
        for device in preferences.devices:
            device.use = device.type != "CPU"
            gpu_count += 1 if device.use else 0
        if gpu_count:
            scene.cycles.device = "GPU"
            print(f"[gpu] {device_type}: {gpu_count}", flush=True)
            break
    except Exception as error:
        print(f"[gpu] {device_type} unavailable: {error}", flush=True)
else:
    scene.cycles.device = "CPU"

scene.cycles.samples = spp
scene.cycles.use_denoising = denoise
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
if TONEMAP == "none":
    raw_path = out_path + ".raw.png"
    scene.render.filepath = raw_path
    bpy.ops.render.render(write_still=True)


def display_post(path, destination):
    # Display-referred approximation of the camera post stack:
    # white balance (temperature), saturation, contrast about mid grey, gamma.
    import numpy

    image = bpy.data.images.load(path)
    image.colorspace_settings.name = "Non-Color"
    width, height = image.size
    pixels = numpy.empty(width * height * 4, dtype=numpy.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)
    rgb = pixels[:, :3]
    temperature = float(post.get("temperature", 6500.0))
    shift = max(-0.5, min(0.5, (6500.0 - temperature) / 6500.0))
    rgb *= numpy.array([1.0 - shift * 0.25, 1.0, 1.0 + shift * 0.25], dtype=numpy.float32)
    luma = (rgb * numpy.array([0.2126, 0.7152, 0.0722], dtype=numpy.float32)).sum(axis=1, keepdims=True)
    rgb[:] = luma + (rgb - luma) * float(post.get("saturation", 1.0))
    rgb[:] = (rgb - 0.5) * float(post.get("contrast", 1.0)) + 0.5
    rgb[:] = numpy.clip(rgb, 0.0, 1.0) ** float(post.get("gamma", 1.0))
    rgb[:] = rgb * float(post.get("gain", 1.0)) + float(post.get("offset", 0.0))
    pixels[:, :3] = numpy.clip(rgb, 0.0, 1.0)
    pixels[:, 3] = 1.0
    output = bpy.data.images.new("post", width, height, alpha=False, float_buffer=False)
    output.colorspace_settings.name = "Non-Color"
    output.pixels.foreach_set(pixels.ravel())
    output.filepath_raw = destination
    output.file_format = "PNG"
    output.save()


def ue_filmic_render(destination):
    # Scene-linear EXR; backdrop hit by camera rays stays transparent so the
    # tonemapper only sees lit geometry, then composite over white.
    import shutil
    import numpy
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ue_filmic import ENGINE_DISPLAY_GRAY, ue_post, ue55_post

    scene.view_settings.exposure = 0.0  # exposure is applied in ue_post on linear data
    scene.render.film_transparent = background_type == "white"
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "32"
    exr_path = destination + ".linear.exr"
    scene.render.filepath = exr_path
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(exr_path)
    image.colorspace_settings.name = "Non-Color"
    width, height = image.size
    pixels = numpy.empty(width * height * 4, dtype=numpy.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)
    exposure_ev = float(post.get("exposure", 0.0)) + EXPOSURE_BIAS_EV
    alpha = pixels[:, 3] if background_type == "white" else numpy.ones(len(pixels), numpy.float32)
    if TONEMAP == "ue55":
        if background_type != "white":
            backdrop = 0.0
        elif DISPLAY_UNITS == "engine":
            # Engine post treats the backdrop as nits. HDRI brightness is the
            # legacy radiance; divide by 1.2 * display gray so that white
            # still lands on the film shoulder.
            backdrop = hdri_brightness / (1.2 * ENGINE_DISPLAY_GRAY)
        else:
            backdrop = hdri_brightness
        pixels[:, :3] = ue55_post(pixels[:, :3], alpha, post, exposure_bias_ev=exposure_ev, background_linear=backdrop, display_units=DISPLAY_UNITS)
    else:
        pixels[:, :3] = ue_post(pixels[:, :3], alpha, post, exposure_ev=exposure_ev)
    pixels[:, 3] = 1.0
    output = bpy.data.images.new("ue_filmic", width, height, alpha=False, float_buffer=False)
    output.colorspace_settings.name = "Non-Color"
    output.pixels.foreach_set(pixels.ravel())
    output.filepath_raw = destination
    output.file_format = "PNG"
    output.save()
    if LINEAR_OUT:
        shutil.copyfile(exr_path, LINEAR_OUT)
    os.remove(exr_path)
    scene.render.film_transparent = False
    print(
        f"[tonemap] ue-filmic exposure_ev={exposure_ev} film_transparent={background_type == 'white'} backdrop={backdrop if TONEMAP == 'ue55' else 0}",
        flush=True,
    )


if TONEMAP == "none":
    display_post(raw_path, out_path)
    os.remove(raw_path)
else:
    ue_filmic_render(out_path)
print(f"[done] {out_path}", flush=True)

if mask_out_path:
    # Coverage mask: transparent film, few samples, alpha is the object mask.
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.render.filepath = mask_out_path + ".rgba.png"
    bpy.ops.render.render(write_still=True)
    import numpy

    rgba = bpy.data.images.load(scene.render.filepath)
    rgba.colorspace_settings.name = "Non-Color"
    width, height = rgba.size
    buffer = numpy.empty(width * height * 4, dtype=numpy.float32)
    rgba.pixels.foreach_get(buffer)
    alpha = (buffer.reshape(-1, 4)[:, 3] > 0.5).astype(numpy.float32)
    gray = numpy.repeat(alpha[:, None], 4, axis=1)
    gray[:, 3] = 1.0
    mask_image = bpy.data.images.new("mask", width, height, alpha=False, float_buffer=False)
    mask_image.colorspace_settings.name = "Non-Color"
    mask_image.pixels.foreach_set(gray.ravel())
    mask_image.filepath_raw = mask_out_path
    mask_image.file_format = "PNG"
    mask_image.save()
    os.remove(scene.render.filepath)
    print(f"[done] {mask_out_path}", flush=True)
