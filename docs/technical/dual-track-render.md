# Dual-track render architecture

## Tracks

- **Preview**: `native/host/target/release/mutracer-render` runs the
  `stage_render` binary. It accepts the stage scene JSON and asset map and is
  the interactive-accuracy track. The cloud worker and `8787` endpoint are
  preview-only; they must not be used as the final renderer.
- **Final**: the current final track is Blender-only. The folded-in
  `tools/dual-track/blender/blender_inner.py` builds the stage scene inside
  headless Blender and renders Cycles. `tools/dual-track/blender/run_blender_final.py`
  is the one-shot CLI. UE native rendering remains a later track; the current
  stage service uses Pixel Streaming with either a mock or real UE backend and is
  not the final image engine.
- Both tracks consume the same scene JSON and asset map, including model,
  camera, environment, and mesh-material identity semantics. See
  `tools/dual-track/stage_semantics.md`.

## Fold-in list

Sources are in `my-stage-hk/local-stack/remote-server/render/`.

| Source | Target / status |
| --- | --- |
| `blender_inner.py` | Folded into `tools/dual-track/blender/blender_inner.py`; accepts the local asset map as a file or JSON object, resolution overrides, and macOS Metal GPU selection. |
| `blender_render.py` | Replaced by `tools/dual-track/blender/run_blender_final.py` for single-shot batch rendering; watch-dir polling is not copied in this round. |
| `bridge.py` | Not folded in. It is the legacy Supabase `render_task` production bridge and is optional future work. |
| `mutracer_render.py` | Kept as reference only. Preview invocation remains in `mutracer-render`; final submission is now routed to Blender. |
| `stage-render-worker.service` | Legacy Blender watch worker for the stage final track. |
| `stage-render-worker-mutracer.service` | Legacy preview worker. Under the mutracer cloud service, the `8787` worker is preview-only. |

## Semantics and asset protocol

- Stage is UE-like Z-up; transforms use `rotation_euler` degrees and the stage
  left-handed convention.
- Preview imports glTF as stage UE coordinates `(-z, x, y)`, normalizes the
  camera matrix final row, and applies `scene.materials` per mesh. See
  `native/host/src/bin/stage_render.rs`.
- Blender applies the same material identity. Scene color, metallic, roughness,
  and texture URLs drive the Principled BSDF; special cases remain for CAD debug
  plastic, charcoal door-edge powder coat, near-white refrigerator drawer faces,
  and transmissive glass. The Blender track has no global metalness or roughness
  clamp.
- Blender uses the folded-in renderer's `C = RotX(90)` conversion for its
  importer's Y-up scene. Camera transforms additionally map the stage camera
  basis to Blender's `-Z` forward view basis. Do not apply the preview glTF
  basis before Blender.
- The asset map maps scene asset URLs to local absolute paths. The folded-in
  Blender renderer accepts `url -> path` JSON either inline or in a file.
  `run_blender_final.py` also accepts the refrigerator entry-list map and
  resolves relative values against `--assets-root` or the map directory.
- HDRI comes from scene textures. `hdri_brightness` is used as Cycles
  Background Strength, capped at 10; mutracer preview scaling is not reused for
  Blender. When the active environment requests `white`, Blender uses the flat
  white world and does not load HDRI.
- Only Blender's built-in glTF importer is required. No Supabase download path
  or special Blender add-on is used.

## Dependencies

- Blender 4.2 LTS or newer on Linux, or Blender 5.x on macOS.
- Cycles GPU: OptiX then CUDA on Linux; Metal on macOS, with CPU fallback.
- Python 3 and Pillow for orchestration, comparison, and metrics.
- The GLB and HDRI files named by the scene and asset map must be locally
  reachable; this repository deliberately does not duplicate them in source
  directories.

## Cloud final track

Use the Ubuntu host with Blender 4.2 LTS and OptiX for remote Cycles. The
orchestration command is the same; set `--blender /usr/local/bin/blender` and
point the asset map at remotely copied files. SSH access is required only for
synchronizing the scene, asset map, referenced GLB/HDRI subset, and scripts; the
public `8787` service remains preview-only. If SSH or the remote Blender path is
unavailable, `run_blender_final.py` remains the local final-track path and the
run summary records the cloud blocker.

## Usage

See `tools/dual-track/README.md` for the direct commands. The comparison output
places preview, final, and reference left to right after resizing to equal
height. Metrics contain brightness standard deviation for each image and
background-difference silhouette IoU for both rendered tracks versus the
reference.
