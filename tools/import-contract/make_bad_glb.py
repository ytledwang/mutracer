#!/usr/bin/env python3
"""Deliberately break a good GLB: strip names, flatten pivots, merge a palette material."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

# Reuse GLB IO from the validator.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_glb import load_gltf, write_glb, PIVOT_RE, _name


def break_contract(doc):
    doc = copy.deepcopy(doc)
    nodes = doc.get("nodes") or []
    meshes = doc.get("meshes") or []
    cameras = doc.get("cameras") or []

    # Flatten: reparent every pivot's children to the scene root and drop the pivot node.
    scenes = doc.get("scenes") or []
    roots = list((scenes[doc.get("scene", 0)] or {}).get("nodes") or []) if scenes else []
    drop = set()
    for i, node in enumerate(nodes):
        if PIVOT_RE.search(_name(node) or ""):
            children = list(node.get("children") or [])
            # put children where the pivot was
            if i in roots:
                idx = roots.index(i)
                roots[idx:idx + 1] = children
            else:
                for parent in nodes:
                    kids = parent.get("children") or []
                    if i in kids:
                        parent["children"] = [c for c in kids if c != i] + children
            node["children"] = []
            drop.add(i)

    if scenes:
        scenes[doc.get("scene", 0)]["nodes"] = [i for i in roots if i not in drop]

    # Strip names
    for i, node in enumerate(nodes):
        if "name" in node:
            del node["name"]
        extras = node.get("extras") or {}
        extras.pop("replace_id", None)
        extras.pop("replaceId", None)
        if extras:
            node["extras"] = extras
        elif "extras" in node:
            del node["extras"]
    for mesh in meshes:
        mesh.pop("name", None)
        for prim in mesh.get("primitives") or []:
            prim["material"] = 0
    for cam in cameras:
        cam.pop("name", None)

    doc["materials"] = [{
        "name": "PaletteMaterial001",
        "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.5},
    }]
    # Leave dropped pivot nodes in the array (indices stay valid) but unused.
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("good", type=Path)
    parser.add_argument("bad", type=Path)
    args = parser.parse_args(argv)
    doc = load_gltf(args.good)
    bad = break_contract(doc)
    args.bad.parent.mkdir(parents=True, exist_ok=True)
    write_glb(bad, args.good, args.bad)
    print(f"wrote {args.bad}")


if __name__ == "__main__":
    main()
