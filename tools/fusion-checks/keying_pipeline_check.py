#!/usr/bin/env python3
"""r6 可影 1.0 渲染链路报告验收。
Exit 0 only if the report cites the gold task id, the engine, and the key numeric
settings with source file paths that actually exist. Exit 1 if a required section
is missing or a cited path does not exist.
Usage: keying_pipeline_check.py [EVIDENCE_DIR]
Default evidence dir: docs/prd/evidence/fusion/fidelity/r6
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DIR = os.path.join(ROOT, "docs/prd/evidence/fusion/fidelity/r6")

REQUIRED_FILES = ("pipeline.md", "conclusion.txt", "sources.json")
REQUIRED_SECTIONS = (
    "场景是谁写的",
    "任务如何提交",
    "渲染引擎",
    "相机后期",
    "材质",
    "输出",
    "其它会影响外观的因素",
    "MuTracer 应如何跟随",
    "尚未核实",
)
REQUIRED_STRINGS = {
    "gold_task_id": "329c202e",
    "engine_ue": "UE 5.5",
    "engine_path_tracing": "Path Tracing",
    "engine_actor": "RenderActor",
    "exposure": "0.8",
    "gamma": "0.9",
    "contrast": "1.2",
    "saturation": "0.8",
    "hdri_brightness": "10",
    "skylight_intensity": "0.35",
    "background_type": "white",
    "aa_spatial_samples": "1024",
    "max_bounces": "32",
    "resolution": "7680",
}

# Paths we expect the report to cite (must exist on this machine).
REQUIRED_EXISTING_PATHS = (
    "/Users/wangjianzheng/Project/HG/dyson/PixelStreaming/Source/PixelStreamingDemo/RenderActor.cpp",
    "/Users/wangjianzheng/Project/HG/dyson/PixelStreaming/Source/PixelStreamingDemo/HaierJsonBlueprintFunctionLibrary.cpp",
    "/Users/wangjianzheng/Project/HG/dyson/PixelStreaming/Source/PixelStreamingDemo/JsonStructs.h",
    "/Users/wangjianzheng/Project/HG/dyson/PixelStreaming/Config/DefaultEngine.ini",
    "/Users/wangjianzheng/Project/HG/dyson/PixelStreaming/PixelStreamingDemo.uproject",
    "/Users/wangjianzheng/Project/HG/my-stage-hk/components/editor/panel/render/dialog.tsx",
    "/Users/wangjianzheng/Project/git/mutracer/docs/prd/evidence/fusion/fidelity/r4/gold-render-task-329c202e-render_data.json",
)


def fail(msg: str) -> None:
    print("FAIL:", msg)
    sys.exit(1)


def main() -> None:
    ev = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR)
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(ev, f))]
    if missing:
        fail(f"missing report files in {ev}: {missing}")

    pipeline = open(os.path.join(ev, "pipeline.md"), encoding="utf-8").read()
    conclusion = open(os.path.join(ev, "conclusion.txt"), encoding="utf-8").read().strip()
    try:
        sources = json.load(open(os.path.join(ev, "sources.json"), encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"sources.json is not valid JSON: {exc}")

    if not conclusion:
        fail("conclusion.txt is empty")

    for section in REQUIRED_SECTIONS:
        if section not in pipeline:
            fail(f"pipeline.md missing required section: {section}")

    for name, needle in REQUIRED_STRINGS.items():
        if needle not in pipeline:
            fail(f"pipeline.md missing required citation {name}: {needle!r}")

    for path in REQUIRED_EXISTING_PATHS:
        if path not in pipeline and path not in json.dumps(sources, ensure_ascii=False):
            fail(f"required source path not cited: {path}")
        if not os.path.exists(path):
            fail(f"cited required path does not exist: {path}")

    # Every 'path' field in sources.json that is not marked missing must exist.
    cited = []

    def walk(node, trail=""):
        if isinstance(node, dict):
            if node.get("missing") is True:
                return
            if "path" in node and isinstance(node["path"], str):
                cited.append((trail + ".path", node["path"], node.get("optional", False)))
            for k, v in node.items():
                if k in ("path", "paths"):
                    if isinstance(v, list):
                        for i, p in enumerate(v):
                            if isinstance(p, str):
                                cited.append((f"{trail}.{k}[{i}]", p, False))
                            elif isinstance(p, dict):
                                walk(p, f"{trail}.{k}[{i}]")
                elif k != "path":
                    walk(v, f"{trail}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{trail}[{i}]")

    walk(sources)
    if len(cited) < 8:
        fail(f"sources.json cites too few paths ({len(cited)})")
    bad = []
    for trail, path, optional in cited:
        if not path or path.startswith("gap:") or path.startswith("unknown:"):
            if not optional:
                bad.append((trail, path, "empty or placeholder without missing=true"))
            continue
        # Allow repo-relative paths
        resolved = path if os.path.isabs(path) else os.path.join(ROOT, path)
        if not os.path.exists(resolved):
            bad.append((trail, path, "does not exist"))
    if bad:
        lines = "\n".join(f"  {t}: {p} ({why})" for t, p, why in bad)
        fail(f"cited path(s) do not exist:\n{lines}")

    # secret sanity on the three deliverables only
    secret = re.compile(rb"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|X-Amz-Signature|AKIA[0-9A-Z]{16}")
    for f in REQUIRED_FILES:
        raw = open(os.path.join(ev, f), "rb").read()
        if secret.search(raw):
            fail(f"secret-like pattern in {f}")

    print("OK", ev, "sections", len(REQUIRED_SECTIONS), "cited_paths", len(cited))


if __name__ == "__main__":
    main()
