#!/usr/bin/env python3
"""r10 light-parent accumulation checker.

Fail-first: written before the blender_inner.py fix. Exit 1 while add_light
still does parent_matrix @ light_basis_from_ue(node) at every root/group
(r9 buggy mirrored poses). Exit 0 only when implementation poses match
"accumulate in UE space, then convert once" (same algorithm as walk()).

Also asserts identity-group parents do not inject an extra
swap_yz @ ue_basis_from_view basis, and that r9 baseline numbers still
describe the pre-fix bug.

Does not require Blender. Does not retune k. Does not render.

Usage:
  python3 tools/fusion-checks/fidelity_r10_light_check.py \
      [--out docs/prd/evidence/fusion/fidelity/r10/check.json] \
      [--dump PATH]   # optional pose dump: [{id, loc, forward}, ...]

Exit 0: implementation matches convert-once expected poses.
Exit 1: still at r9 buggy poses, or mismatch / failed assertion.
Exit 2: usage / unreadable input.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
R9_LIGHTS = REPO / "docs/prd/evidence/fusion/fidelity/r9-analysis/lights.json"
STOVE_SCENE = REPO / "docs/prd/evidence/fusion/fidelity/r8/scene-00ac0cff-preview.json"
INNER = REPO / "tools/dual-track/blender/blender_inner.py"
RECT24_ID = "ca05c81b-d2e9-4cb6-947a-9bef54a38283"
RECT24_DELTA_M = 6.593389
LOC_TOL = 1e-5
FWD_TOL = 1e-5
# r9 vlist used round(..., 6); allow one rounding ulp on dumped numbers.
R9_TOL = 1.5e-6

# ---------------------------------------------------------------------------
# Minimal Matrix, matching mathutils row-index convention used in blender_inner
# ---------------------------------------------------------------------------


class Matrix:
    def __init__(self, rows):
        self._m = [[float(v) for v in row] for row in rows]

    @staticmethod
    def Identity(n=4):
        return Matrix([[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)])

    def copy(self):
        return Matrix(self._m)

    def __getitem__(self, i):
        return self._m[i]

    def __setitem__(self, i, row):
        self._m[i] = row

    def __matmul__(self, other):
        if isinstance(other, Matrix):
            n = 4
            out = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    s = 0.0
                    for k in range(n):
                        s += self._m[i][k] * other._m[k][j]
                    out[i][j] = s
            return Matrix(out)
        vec = list(other)
        return tuple(sum(self._m[i][k] * vec[k] for k in range(4)) for i in range(4))

    def to_translation(self):
        return (self._m[0][3], self._m[1][3], self._m[2][3])


def identity():
    return Matrix.Identity(4)


def swap_yz():
    return Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
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


def light_basis_from_ue(entity):
    return sanitize(swap_yz() @ ue_local_matrix(entity) @ ue_basis_from_view())


def light_world_from_ue(ue_local):
    return sanitize(swap_yz() @ ue_local @ ue_basis_from_view())


def vlist(v, nd=6):
    return [round(float(v[i]), nd) for i in range(3)]


def forward_minus_z(matrix):
    x, y, z, _w = matrix @ (0.0, 0.0, -1.0, 0.0)
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / n, y / n, z / n)


def dist(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def close_vec(a, b, tol):
    return dist(a, b) <= tol


def load_scene(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("scene_json", raw)


# ---------------------------------------------------------------------------
# Independent reference: buggy (r9) vs correct (UE-accumulate, convert once)
# ---------------------------------------------------------------------------


def walk_buggy(lights, light_id, parent_matrix, depth, out, group_out):
    node = lights.get(light_id)
    if not node or node.get("is_visible") is False:
        return
    matrix = parent_matrix @ light_basis_from_ue(node)
    if node.get("type") != "light":
        group_out.append({
            "id": light_id,
            "name": node.get("name"),
            "type": node.get("type"),
            "depth": depth,
            "child_parent_is_identity": _is_identity(matrix),
            "injected_extra_basis": not _is_identity(matrix) and _is_identity(parent_matrix) and _is_identity(ue_local_matrix(node)),
        })
    if node.get("type") == "light":
        data = node.get("light") or {}
        out.append(_record(node, light_id, depth, data, matrix))
    for child in node.get("children", []) or []:
        walk_buggy(lights, child, matrix, depth + 1, out, group_out)


def walk_correct(lights, light_id, parent_ue, depth, out, group_out):
    node = lights.get(light_id)
    if not node or node.get("is_visible") is False:
        return
    ue = parent_ue @ ue_local_matrix(node)
    if node.get("type") != "light":
        group_out.append({
            "id": light_id,
            "name": node.get("name"),
            "type": node.get("type"),
            "depth": depth,
            "child_parent_is_identity": _is_identity(ue),
            "injected_extra_basis": not _is_identity(ue) and _is_identity(parent_ue) and _is_identity(ue_local_matrix(node)),
        })
    if node.get("type") == "light":
        matrix = light_world_from_ue(ue)
        data = node.get("light") or {}
        out.append(_record(node, light_id, depth, data, matrix))
    for child in node.get("children", []) or []:
        walk_correct(lights, child, ue, depth + 1, out, group_out)


def _is_identity(m, tol=1e-9):
    for i in range(4):
        for j in range(4):
            expected = 1.0 if i == j else 0.0
            if abs(m[i][j] - expected) > tol:
                return False
    return True


def _record(node, light_id, depth, data, matrix):
    loc = matrix.to_translation()
    fwd = forward_minus_z(matrix)
    return {
        "name": node.get("name"),
        "id": light_id,
        "depth": depth,
        "type": data.get("type"),
        "power_raw": data.get("power"),
        "loc": vlist(loc),
        "forward": vlist(fwd),
        "loc_raw": [float(loc[i]) for i in range(3)],
        "forward_raw": [float(fwd[i]) for i in range(3)],
    }


def simulate_scene(scene, walker):
    lights = scene.get("lights") or {}
    out, groups = [], []
    for light_id, node in lights.items():
        if node.get("type") == "root":
            walker(lights, light_id, identity(), 0, out, groups)
    return out, groups


# ---------------------------------------------------------------------------
# Execute add_light from blender_inner.py with bpy stubbed (pose only)
# ---------------------------------------------------------------------------


def _functions(src: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(src)
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _called_names(fn: ast.FunctionDef) -> set[str]:
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def extract_add_light_bundle(src: str) -> str:
    fns = _functions(src)
    if "add_light" not in fns:
        raise RuntimeError("blender_inner.py has no def add_light")
    needed = {"add_light"}
    queue = ["add_light"]
    while queue:
        name = queue.pop()
        for callee in _called_names(fns[name]) if name in fns else []:
            if callee in fns and callee not in needed:
                needed.add(callee)
                queue.append(callee)
    # Keep only math helpers + add_light; drop mesh/import helpers that need bpy.
    drop = {
        "add_instance", "walk", "early_camera_matrix", "instance_side",
        "is_cad_debug_name", "material_override", "stage_faithful_override",
        "blender_material", "assign_stage_materials", "world_background",
        "load_environment_node", "display_post", "ue_filmic_render",
        "load_assets", "load_scene", "arg", "mesh_basis_from_ue",
        "blender_gltf_import_basis", "gltf_to_ue", "camera_basis_from_ue",
    }
    keep = [n for n in needed if n not in drop]
    # Preserve source order
    order = [name for name, _ in sorted(
        ((n, fns[n].lineno) for n in keep), key=lambda kv: kv[1]
    )]
    parts = [ast.unparse(fns[n]) for n in order]
    return "\n\n".join(parts)


class _Light:
    def __init__(self, name, typ):
        self.name = name
        self.type = typ
        self.shape = None
        self.size = 0.0
        self.size_y = 0.0
        self.shadow_soft_size = 0.0
        self.spot_size = 0.0
        self.spot_blend = 0.0
        self.color = None
        self.energy = 0.0


class _Obj:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.matrix_world = None


class _Bpy:
    def __init__(self, sink):
        self.sink = sink
        self.data = self
        self.context = self
        self.scene = self
        self.collection = self
        self.objects = self
        self.lights = self

    def new(self, name, type=None):
        # lights.new(name, type=...) or objects.new(name, data)
        if type in ("AREA", "POINT", "SUN", "SPOT") or (
            isinstance(type, str) and type.isupper()
        ):
            return _Light(name, type)
        obj = _Obj(name, type)
        self.sink.append(obj)
        return obj

    def link(self, _obj):
        return None


def exec_impl_poses(inner_src: str, scene: dict) -> tuple[list[dict], list[dict], str]:
    bundle = extract_add_light_bundle(inner_src)
    sink: list[_Obj] = []
    bpy = _Bpy(sink)
    g = {
        "__name__": "blender_inner_light_slice",
        "math": math,
        "Matrix": Matrix,
        "bpy": bpy,
        "stage_scene": scene,
        "LIGHT_UNITS": "candela",
        "AREA_LIGHT_ENERGY_PER_POWER": 1.0,
        "has_stage_light": False,
        "print": lambda *a, **k: None,
    }
    exec(compile(bundle, "blender_inner_light_slice.py", "exec"), g)
    add_light = g["add_light"]
    ident = g["identity"]() if "identity" in g else identity()
    lights = scene.get("lights") or {}
    for light_id, node in lights.items():
        if node.get("type") == "root":
            add_light(light_id, ident, set())
    # Map 8-char object names back to full ids
    by_prefix = {}
    for lid, node in lights.items():
        if node.get("type") == "light":
            by_prefix.setdefault(lid[:8], []).append((lid, node))
    poses = []
    for obj in sink:
        matches = by_prefix.get(obj.name, [])
        if len(matches) != 1:
            raise RuntimeError(f"cannot map light object {obj.name!r} to a unique id")
        lid, node = matches[0]
        data = node.get("light") or {}
        matrix = obj.matrix_world
        if matrix is None:
            raise RuntimeError(f"light {lid} has no matrix_world")
        rec = _record(node, lid, None, data, matrix)
        rec["energy"] = getattr(obj.data, "energy", None)
        poses.append(rec)
    return poses, [], bundle


# ---------------------------------------------------------------------------
# Optional dump
# ---------------------------------------------------------------------------


def load_dump(path: Path) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw
    if isinstance(raw, dict):
        items = raw.get("lights") or raw.get("poses") or raw.get("comparison") or raw
        if isinstance(items, dict):
            items = list(items.values())
    out = {}
    for item in items:
        lid = item.get("id") or item.get("light_id")
        if not lid:
            continue
        loc = item.get("loc") or item.get("applied_loc") or item.get("correct_loc") or item.get("position")
        fwd = item.get("forward") or item.get("applied_forward") or item.get("applied_forward_minusZ") or item.get("correct_forward")
        out[lid] = {"loc": loc, "forward": fwd, "raw": item}
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=STOVE_SCENE)
    parser.add_argument("--r9-lights", type=Path, default=R9_LIGHTS)
    parser.add_argument("--inner", type=Path, default=INNER)
    parser.add_argument("--dump", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv[1:])

    missing = [str(p) for p in (args.scene, args.r9_lights, args.inner) if not p.is_file()]
    if missing:
        print("FAIL: missing input:\n  " + "\n  ".join(missing))
        return 2

    scene = load_scene(args.scene)
    r9 = json.loads(args.r9_lights.read_text(encoding="utf-8"))
    inner_src = args.inner.read_text(encoding="utf-8")

    failures: list[str] = []
    buggy, buggy_groups = simulate_scene(scene, walk_buggy)
    expected, expected_groups = simulate_scene(scene, walk_correct)

    if len(buggy) != 13 or len(expected) != 13:
        failures.append(f"expected 13 stove lights, got buggy={len(buggy)} expected={len(expected)}")

    # Independent sim must reproduce r9 baseline (bug) and r9 "correct" poses.
    r9_by_id = {row["id"]: row for row in r9["comparison"]}
    for rec in buggy:
        ref = r9_by_id.get(rec["id"])
        if ref is None:
            failures.append(f"r9 comparison missing {rec['name']}")
            continue
        if not close_vec(rec["loc"], ref["applied_loc"], R9_TOL):
            failures.append(f"independent buggy loc != r9 applied for {rec['name']}: {rec['loc']} vs {ref['applied_loc']}")
        if not close_vec(rec["forward"], ref["applied_forward"], R9_TOL):
            failures.append(f"independent buggy forward != r9 applied for {rec['name']}: {rec['forward']} vs {ref['applied_forward']}")
    for rec in expected:
        ref = r9_by_id.get(rec["id"])
        if ref is None:
            continue
        if not close_vec(rec["loc"], ref["correct_loc"], R9_TOL):
            failures.append(f"independent correct loc != r9 correct for {rec['name']}: {rec['loc']} vs {ref['correct_loc']}")
        if not close_vec(rec["forward"], ref["correct_forward"], R9_TOL):
            failures.append(f"independent correct forward != r9 correct for {rec['name']}: {rec['forward']} vs {ref['correct_forward']}")

    r24_buggy = next(r for r in buggy if r["id"] == RECT24_ID)
    r24_exp = next(r for r in expected if r["id"] == RECT24_ID)
    delta = dist(r24_buggy["loc_raw"], r24_exp["loc_raw"])
    if abs(delta - RECT24_DELTA_M) > 1e-5:
        failures.append(f"RectLight24 independent delta {delta:.6f} != r9 {RECT24_DELTA_M}")
    if r24_buggy["loc"][2] <= 0 or r24_exp["loc"][2] >= 0:
        failures.append(
            f"RectLight24 z signs unexpected: buggy z={r24_buggy['loc'][2]} expected z={r24_exp['loc'][2]}"
        )

    # Identity groups: buggy path injects extra basis; correct path must not.
    if not any(g["injected_extra_basis"] for g in buggy_groups):
        failures.append("self-check: buggy path did not inject extra basis on identity groups")
    if any(g["injected_extra_basis"] for g in expected_groups):
        failures.append("self-check: correct path injected extra basis on identity groups")
    if not all(g["child_parent_is_identity"] for g in expected_groups):
        failures.append("self-check: correct identity-group parent passed to children is not identity")

    # Implementation poses from current blender_inner.py
    impl_error = None
    impl_poses: list[dict] = []
    try:
        impl_poses, _, bundle = exec_impl_poses(inner_src, scene)
    except Exception as exc:
        impl_error = f"{type(exc).__name__}: {exc}"
        failures.append(f"failed to execute add_light from blender_inner.py: {impl_error}")
        bundle = ""

    impl_by_id = {r["id"]: r for r in impl_poses}
    exp_by_id = {r["id"]: r for r in expected}
    bug_by_id = {r["id"]: r for r in buggy}
    n_match_expected = 0
    n_match_buggy = 0
    per_light = []
    for rec in expected:
        lid = rec["id"]
        impl = impl_by_id.get(lid)
        row = {
            "name": rec["name"],
            "id": lid,
            "depth": rec["depth"],
            "r9_buggy_loc": bug_by_id[lid]["loc"],
            "expected_loc": rec["loc"],
            "r9_buggy_forward": bug_by_id[lid]["forward"],
            "expected_forward": rec["forward"],
            "impl_loc": impl["loc"] if impl else None,
            "impl_forward": impl["forward"] if impl else None,
            "delta_impl_vs_expected_m": None,
            "delta_impl_vs_buggy_m": None,
            "matches_expected": False,
            "matches_buggy": False,
        }
        if impl:
            row["delta_impl_vs_expected_m"] = round(dist(impl["loc_raw"], rec["loc_raw"]), 6)
            row["delta_impl_vs_buggy_m"] = round(dist(impl["loc_raw"], bug_by_id[lid]["loc_raw"]), 6)
            row["matches_expected"] = close_vec(impl["loc_raw"], rec["loc_raw"], LOC_TOL) and close_vec(impl["forward_raw"], rec["forward_raw"], FWD_TOL)
            row["matches_buggy"] = close_vec(impl["loc_raw"], bug_by_id[lid]["loc_raw"], LOC_TOL) and close_vec(impl["forward_raw"], bug_by_id[lid]["forward_raw"], FWD_TOL)
            n_match_expected += int(row["matches_expected"])
            n_match_buggy += int(row["matches_buggy"])
        per_light.append(row)

    still_buggy = bool(impl_poses) and n_match_buggy == 13 and n_match_expected == 0
    all_expected = bool(impl_poses) and n_match_expected == 13
    if impl_poses and not all_expected:
        if still_buggy:
            failures.append(
                "implementation still uses parent_matrix @ light_basis_from_ue(node); "
                "all 13 stove lights remain at the r9 buggy mirrored pose "
                f"(RectLight24 at {impl_by_id[RECT24_ID]['loc']}, expected {exp_by_id[RECT24_ID]['loc']})"
            )
        else:
            failures.append(
                f"implementation poses match expected {n_match_expected}/13, "
                f"match r9 buggy {n_match_buggy}/13"
            )

    # Identity-group injection inferred from implementation vs expected/buggy.
    # If impl matches expected, identity groups did not inject extra basis.
    identity_ok = all_expected
    if still_buggy:
        failures.append("identity-group parents still inject swap_yz @ ue_basis_from_view")

    dump_info = None
    if args.dump:
        if not args.dump.is_file():
            failures.append(f"dump not found: {args.dump}")
        else:
            dumped = load_dump(args.dump)
            dump_rows = []
            n_ok = 0
            for rec in expected:
                d = dumped.get(rec["id"])
                ok = bool(d and d.get("loc") and close_vec(d["loc"], rec["loc"], LOC_TOL))
                n_ok += int(ok)
                dump_rows.append({
                    "id": rec["id"],
                    "name": rec["name"],
                    "dump_loc": d.get("loc") if d else None,
                    "expected_loc": rec["loc"],
                    "matches_expected": ok,
                })
                if d and d.get("loc") and close_vec(d["loc"], bug_by_id[rec["id"]]["loc"], LOC_TOL):
                    failures.append(f"dump still at r9 buggy pose for {rec['name']}")
            if n_ok != 13:
                failures.append(f"dump matches expected {n_ok}/13")
            dump_info = {"path": str(args.dump), "n_match_expected": n_ok, "lights": dump_rows}

    r24_impl = impl_by_id.get(RECT24_ID)
    report = {
        "round": "r10",
        "title": "light parent accumulation: UE-space then convert once",
        "result": "FAIL" if failures else "PASS",
        "scene": str(args.scene),
        "inner": str(args.inner),
        "r9_lights": str(args.r9_lights),
        "n_stove_lights": len(expected),
        "n_match_expected": n_match_expected,
        "n_match_buggy": n_match_buggy,
        "still_at_r9_buggy_poses": still_buggy,
        "identity_group_parents_clean": identity_ok,
        "impl_exec_error": impl_error,
        "RectLight24": {
            "id": RECT24_ID,
            "r9_buggy_loc": r24_buggy["loc"],
            "expected_loc": r24_exp["loc"],
            "r9_buggy_forward": r24_buggy["forward"],
            "expected_forward": r24_exp["forward"],
            "impl_loc": r24_impl["loc"] if r24_impl else None,
            "impl_forward": r24_impl["forward"] if r24_impl else None,
            "r9_delta_m": RECT24_DELTA_M,
            "independent_delta_m": round(delta, 6),
        },
        "identity_groups_independent": {
            "buggy_injects": [g for g in buggy_groups if g["injected_extra_basis"]],
            "correct_injects": [g for g in expected_groups if g["injected_extra_basis"]],
        },
        "lights": per_light,
        "dump": dump_info,
        "failures": failures,
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)
    print(f"RESULT {report['result']} failures={len(failures)}")
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
