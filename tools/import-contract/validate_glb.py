#!/usr/bin/env python3
"""Validate a GLB/glTF against the MuTracer import contract (names are the contract)."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

GENERIC_NODE = re.compile(r"^(Node|Mesh|Object|Empty|Cube|Cylinder|Sphere|Icosphere)([._\s-]?\d+)?$", re.I)
GENERIC_MESH = re.compile(r"^(Mesh|Geometry)([._\s-]?\d+)?$", re.I)
GENERIC_MAT = re.compile(r"^(Material|DefaultMaterial|Default|DefaultMaterial\.?\d*)([._\s-]?\d+)?$", re.I)
PALETTE_MAT = re.compile(r"^PaletteMaterial", re.I)
PIVOT_RE = re.compile(r"pivot", re.I)


def load_gltf(path: Path):
    data = path.read_bytes()
    if len(data) >= 12 and data[:4] == b"glTF":
        _magic, version, length = struct.unpack_from("<4sII", data, 0)
        if version != 2:
            raise ValueError(f"unsupported GLB version {version}")
        offset = 12
        json_chunk = None
        while offset + 8 <= min(length, len(data)):
            chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
            offset += 8
            chunk = data[offset:offset + chunk_len]
            offset += chunk_len
            if chunk_type == b"JSON":
                json_chunk = chunk
                break
        if json_chunk is None:
            raise ValueError("GLB has no JSON chunk")
        return json.loads(json_chunk.decode("utf-8"))
    return json.loads(data.decode("utf-8"))


def write_glb(doc, src: Path, dest: Path):
    """Rewrite JSON chunk of a GLB, preserving the BIN chunk when present."""
    raw = src.read_bytes()
    if raw[:4] != b"glTF":
        dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return
    _magic, version, length = struct.unpack_from("<4sII", raw, 0)
    offset = 12
    bin_chunk = b""
    while offset + 8 <= min(length, len(raw)):
        chunk_len, chunk_type = struct.unpack_from("<I4s", raw, offset)
        offset += 8
        chunk = raw[offset:offset + chunk_len]
        offset += chunk_len
        if chunk_type == b"BIN\x00":
            bin_chunk = chunk
            break
    json_bytes = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    while len(json_bytes) % 4:
        json_bytes += b" "
    parts = [b"glTF", struct.pack("<I", 2)]
    body = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    if bin_chunk:
        while len(bin_chunk) % 4:
            bin_chunk += b"\x00"
        body += struct.pack("<I4s", len(bin_chunk), b"BIN\x00") + bin_chunk
    total = 12 + len(body)
    dest.write_bytes(b"glTF" + struct.pack("<II", 2, total) + body)


def _name(item):
    if not isinstance(item, dict):
        return ""
    return (item.get("name") or "").strip()


def dump_names(doc):
    nodes = doc.get("nodes") or []
    meshes = doc.get("meshes") or []
    materials = doc.get("materials") or []
    cameras = doc.get("cameras") or []
    scenes = doc.get("scenes") or []
    root_indices = list((scenes[doc.get("scene", 0)] or {}).get("nodes") or []) if scenes else []

    def parent_map():
        parents = {i: None for i in range(len(nodes))}
        for i, node in enumerate(nodes):
            for child in node.get("children") or []:
                parents[child] = i
        return parents

    parents = parent_map()
    node_rows = []
    pivots = []
    placeholders = []
    camera_names = []
    for i, node in enumerate(nodes):
        name = _name(node)
        kind = "node"
        if "mesh" in node:
            kind = "mesh"
        if "camera" in node:
            kind = "camera"
            camera_names.append(name)
        extras = node.get("extras") or {}
        parent = parents.get(i)
        node_rows.append({
            "index": i,
            "name": name,
            "parent": None if parent is None else _name(nodes[parent]),
            "parentIndex": parent,
            "kind": kind,
            "mesh": node.get("mesh"),
            "camera": node.get("camera"),
            "extras": extras or None,
        })
        if PIVOT_RE.search(name):
            pivots.append(name)
        rid = extras.get("replace_id") or extras.get("replaceId")
        if rid or name:
            if rid:
                placeholders.append({"name": name, "replace_id": rid})

    return {
        "version": "mutracer-names/1",
        "source": "gltf",
        "nodes": node_rows,
        "meshes": [{"index": i, "name": _name(m)} for i, m in enumerate(meshes)],
        "materials": [{"index": i, "name": _name(m),
                       "baseColorFactor": ((m.get("pbrMetallicRoughness") or {}).get("baseColorFactor"))}
                      for i, m in enumerate(materials)],
        "cameras": camera_names or [_name(c) for c in cameras],
        "pivots": pivots,
        "placeholders": placeholders,
        "rootIndices": root_indices,
    }


def _issue(issues, severity, code, message):
    issues.append({"severity": severity, "code": code, "message": message})
    prefix = {"error": "ERROR", "warning": "WARN", "info": "INFO"}[severity]
    print(f"{prefix} [{code}] {message}")


def validate(doc, args):
    issues = []
    nodes = doc.get("nodes") or []
    meshes = doc.get("meshes") or []
    materials = doc.get("materials") or []
    cameras = doc.get("cameras") or []

    named_nodes = []
    pivot_indices = []
    for i, node in enumerate(nodes):
        name = _name(node)
        has_payload = "mesh" in node or "camera" in node
        if has_payload and not name:
            _issue(issues, "error", "node.unnamed", f"node[{i}] has a mesh/camera but no name")
        elif not name and (node.get("children") or has_payload):
            _issue(issues, "warning", "node.unnamed", f"node[{i}] has no name")
        if name and GENERIC_NODE.match(name) and has_payload:
            _issue(issues, "warning", "node.generic", f"node[{i}] has generic name {name!r}")
        if name:
            named_nodes.append(name)
        if name and PIVOT_RE.search(name):
            pivot_indices.append(i)
            children = node.get("children") or []
            if not children and "mesh" not in node:
                _issue(issues, "error", "pivot.empty", f"pivot node {name!r} has no children and no mesh")

    seen = {}
    for name in named_nodes:
        seen[name] = seen.get(name, 0) + 1
    for name, count in seen.items():
        if count > 1:
            _issue(issues, "warning", "node.duplicate", f"duplicate node name {name!r} appears {count} times")

    for i, mesh in enumerate(meshes):
        name = _name(mesh)
        if not name:
            _issue(issues, "warning", "mesh.unnamed", f"mesh[{i}] has no name")
        elif GENERIC_MESH.match(name):
            _issue(issues, "warning", "mesh.generic", f"mesh[{i}] has generic name {name!r}")
        for p, prim in enumerate(mesh.get("primitives") or []):
            if "material" not in prim:
                severity = "warning" if args.allow_missing_materials else "error"
                _issue(issues, severity, "material.missing",
                       f"mesh[{i}] primitive[{p}] has no material")

    palette = False
    generic_only = True
    any_material = False
    for i, mat in enumerate(materials):
        any_material = True
        name = _name(mat)
        if not name:
            _issue(issues, "error", "material.unnamed", f"material[{i}] has no name")
            generic_only = False
            continue
        if PALETTE_MAT.match(name):
            palette = True
            _issue(issues, "error", "material.palette",
                   f"material[{i}] name {name!r} looks like a palette merge")
            generic_only = False
        elif GENERIC_MAT.match(name):
            _issue(issues, "warning", "material.generic", f"material[{i}] has generic name {name!r}")
        else:
            generic_only = False
    if any_material and generic_only and materials:
        _issue(issues, "warning", "material.default_only",
               "every material uses a generic default name")
    if not materials and meshes and not args.allow_missing_materials:
        _issue(issues, "error", "material.none", "file has meshes but no materials")

    if args.require_pivot and not pivot_indices:
        _issue(issues, "error", "pivot.missing", "no node name contains 'Pivot'")
    for expected in args.expect_pivot or []:
        if not any(_name(nodes[i]) == expected or _name(nodes[i]).lower() == expected.lower()
                   for i in range(len(nodes))):
            # also allow substring match on pivot list
            if not any(expected.lower() == _name(n).lower() for n in nodes):
                _issue(issues, "error", "pivot.expected", f"expected pivot node {expected!r} was not found")

    camera_node_names = [_name(n) for n in nodes if "camera" in n]
    if args.require_camera and not camera_node_names and not cameras:
        _issue(issues, "error", "camera.missing", "no camera nodes found")

    if args.placeholder:
        token = args.placeholder
        found = False
        for node in nodes:
            extras = node.get("extras") or {}
            rid = str(extras.get("replace_id") or extras.get("replaceId") or "")
            if _name(node) == token or rid == token:
                found = True
                break
        if not found:
            _issue(issues, "error", "placeholder.missing",
                   f"placeholder / replace_id {token!r} was not found")

    if args.source_units == "mm":
        scale = args.unit_scale
        if scale is None or abs(scale - 1.0) < 1e-9:
            _issue(issues, "warning", "units.no_conversion",
                   "source units are mm and no unit scale was applied (glTF is meters); "
                   "mm→m conversion is a known gap, not a silent success")
        elif abs(scale - 0.001) > 1e-6:
            _issue(issues, "warning", "units.unexpected_scale",
                   f"source units are mm but unit scale is {scale}, not 0.001")

    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text())
        _compare_baseline(doc, baseline, issues)

    # palette already reported; keep a combined note
    if palette:
        pass
    return issues


def _compare_baseline(doc, baseline, issues):
    current = dump_names(doc)
    def nameset(rows, key="name"):
        return {row[key] for row in rows if row.get(key)}

    base_nodes = nameset(baseline.get("nodes") or [])
    now_nodes = nameset(current.get("nodes") or [])
    lost_nodes = sorted(base_nodes - now_nodes)
    if lost_nodes:
        _issue(issues, "error", "baseline.node_lost",
               "optimized export dropped node names: " + ", ".join(lost_nodes))

    base_mats = nameset(baseline.get("materials") or [])
    now_mats = nameset(current.get("materials") or [])
    lost_mats = sorted(base_mats - now_mats)
    if lost_mats:
        _issue(issues, "error", "baseline.material_lost",
               "optimized export dropped material names: " + ", ".join(lost_mats))

    base_pivots = set(baseline.get("pivots") or [])
    now_pivots = set(current.get("pivots") or [])
    lost_pivots = sorted(base_pivots - now_pivots)
    if lost_pivots:
        _issue(issues, "error", "baseline.pivot_lost",
               "optimized export dropped Pivot nodes: " + ", ".join(lost_pivots))

    base_cams = set(baseline.get("cameras") or [])
    now_cams = set(current.get("cameras") or [])
    lost_cams = sorted(base_cams - now_cams)
    if lost_cams:
        _issue(issues, "error", "baseline.camera_lost",
               "optimized export dropped cameras: " + ", ".join(lost_cams))

    # parent relationship for shared names
    def parent_of(rows):
        return {row["name"]: row.get("parent") for row in rows if row.get("name")}
    base_parent = parent_of(baseline.get("nodes") or [])
    now_parent = parent_of(current.get("nodes") or [])
    for name, parent in base_parent.items():
        if name in now_parent and now_parent[name] != parent and parent:
            # flattening typically reparents to None / scene root
            _issue(issues, "error", "baseline.reparented",
                   f"node {name!r} parent was {parent!r}, now {now_parent[name]!r}")

    def color_of(rows, name):
        for row in rows:
            if row.get("name") == name:
                return row.get("baseColorFactor")
        return None
    for name in base_mats & now_mats:
        before = color_of(baseline.get("materials") or [], name)
        after = color_of(current.get("materials") or [], name)
        if before and after and len(before) >= 3 and len(after) >= 3:
            delta = sum(abs(float(a) - float(b)) for a, b in zip(before[:3], after[:3]))
            if delta > 0.05:
                _issue(issues, "error", "baseline.basecolor_washed",
                       f"material {name!r} baseColorFactor changed {before} -> {after}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate GLB/glTF import contract")
    parser.add_argument("glb", type=Path)
    parser.add_argument("--dump-names", type=Path)
    parser.add_argument("--baseline", type=Path, help="names JSON to compare after an optimized export")
    parser.add_argument("--expect-pivot", action="append", default=[], help="Required pivot node name (repeatable)")
    parser.add_argument("--require-pivot", action="store_true")
    parser.add_argument("--require-camera", action="store_true")
    parser.add_argument("--placeholder", help="Require a node name or extras.replace_id")
    parser.add_argument("--allow-missing-materials", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    parser.add_argument("--source-units", choices=["mm", "m"])
    parser.add_argument("--unit-scale", type=float, default=None)
    args = parser.parse_args(argv)

    if not args.glb.is_file():
        print(f"ERROR [file.missing] {args.glb} does not exist", file=sys.stderr)
        return 2

    try:
        doc = load_gltf(args.glb)
    except Exception as exc:
        print(f"ERROR [file.parse] {exc}", file=sys.stderr)
        return 2

    names = dump_names(doc)
    if args.dump_names:
        args.dump_names.parent.mkdir(parents=True, exist_ok=True)
        args.dump_names.write_text(json.dumps(names, indent=2, ensure_ascii=False) + "\n")

    issues = validate(doc, args)
    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    failed = errors > 0 or (args.strict and warnings > 0)
    status = "FAIL" if failed else "PASS"
    print(f"RESULT {status} errors={errors} warnings={warnings} file={args.glb}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
