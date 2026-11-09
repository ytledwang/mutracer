# Import smoke (M3)

Checks which CAD/mesh formats reach a MuTracer render. Summary table:
[`docs/technical/import-greenpath-m3.md`](../../docs/technical/import-greenpath-m3.md).

```bash
tools/import-smoke/smoke.sh      # needs native/host/target/release/mutracer-render, Pillow, Blender
```

Outputs go to `tools/import-smoke/out/`.

## GLB (direct)

Viewer path: `ViewerEngine.loadFiles` (`viewer/src/engine/ViewerEngine.ts`) picks the first model file,
then `loadModelFromFiles` → `loadModelFromSource` → `parseModelSource` (`viewer/src/engine/loadModel.ts`),
which parses `.glb` / `.gltf` with Three.js `GLTFLoader`. `.pbrt` is handled separately; any other extension is rejected with a toast.
Parsing is covered by `viewer/tests/viewerModelLoading.test.ts` (10 tests pass).
To try it by hand: `npm run viewer`, then drop `examples/assets/chess.glb` onto the page.

Headless render of the same asset (native `mutracer-render`, scene from the cloud POC):

```bash
native/host/target/release/mutracer-render \
  --scene tools/cloud-service/poc-out/scene.json \
  --asset-map tools/cloud-service/poc-out/assets.json \
  --out tools/import-smoke/out/chess-256-lookat.png \
  --camera-mode lookat --width 256 --height 256 --samples 16 --bounces 3 --denoise 0 \
  --camera-target 0,0,0 --light-scale 1
```

`--camera-mode lookat` is required for this scene. With the defaults (`--basis ue --camera-mode matrix`)
the output is a uniformly white image (1 unique color), because the POC scene uses glTF Y-up camera
coordinates. `--basis none|stage2y` with either camera mode also renders.

Evidence: `tools/import-smoke/out/chess-256-lookat.png` (4492 unique colors, rook and pawns visible).
Earlier POC renders, not regenerated: `tools/cloud-service/poc-out/local-chess-256.png`, `local-chess-256-verify.png`.

## Converting FBX and STEP to GLB

The viewer loads only GLB/glTF/PBRT. Dropping or picking `.fbx`, `.stp` or `.step` shows a toast pointing at the scripts below (`isConvertibleModelFile` / `convertHint` in `viewer/src/engine/droppedFiles.ts`); the home page drop zone shows the same message. Nothing from FBX or OpenCASCADE enters the browser bundle. Open the resulting `.glb` as usual.

```bash
export BLENDER=/Applications/Blender.app/Contents/MacOS/Blender   # optional if blender is on PATH
tools/import-smoke/convert_fbx_to_glb.sh in.fbx [out.glb]             # Blender import_scene.fbx -> export_scene.gltf
tools/import-smoke/convert_stp_to_glb.sh in.stp|.step|.stl [out.glb]  # gmsh -> STL -> Blender -> GLB
```

`convert_stp_to_glb.sh` uses `gmsh` on PATH, else the `gmsh` Python module of `$GMSH_PYTHON` (default `python3`).
An `.stl` input skips gmsh. `brew install gmsh` is blocked in this sandbox (Homebrew directories not writable), so gmsh came from a venv:

```bash
python3 -m venv /tmp/gmsh-venv && /tmp/gmsh-venv/bin/pip install gmsh
export GMSH_PYTHON=/tmp/gmsh-venv/bin/python
```

`pip install --target` drops `libgmsh.dylib`; use a venv. The wheel's `bin/gmsh` is a Python wrapper, not a native CLI.

Fixtures (`fixtures/`): `sample.fbx` (533 KB, copied from a my-stage-hk backup asset; not a public asset) and `box.step` (10 mm cube written by gmsh/OpenCASCADE, 15 KB).
`smoke.sh` steps 4 and 5 run both conversions into `out/`.

Results: `out/sample-fbx.glb` (486,928 bytes, glTF v2, 25 meshes, 10 materials) and `out/box-stp.glb` (12,360 bytes, 1 mesh, no material). Neither GLB was rendered or opened in a browser.

Limits: units are not converted (STEP is mm, glTF m); gmsh output has no material; FBX animation and skinning are whatever Blender's glTF exporter keeps; `tools/cloud-relay.py` (ssh) was not run.
