# Import green path, M3

Which input formats reach a MuTracer render today. Reproduce with
[`tools/import-smoke/smoke.sh`](../../tools/import-smoke/README.md).

| Format | Status | What works | Gap | Evidence |
| --- | --- | --- | --- | --- |
| GLB / glTF | Green | Viewer: `ViewerEngine.loadFiles` → `loadModelFromFiles` → `parseModelSource` (Three.js `GLTFLoader`). Native: `mutracer-render` renders `chess.glb` | Default `mutracer-render` flags (`--basis ue --camera-mode matrix`) give a blank white image for the POC scene; use `--camera-mode lookat`. Viewer not exercised in a browser this session; covered by `viewer/tests/viewerModelLoading.test.ts` (10 pass) | `tools/import-smoke/out/chess-256-lookat.png`; `tools/cloud-service/poc-out/local-chess-256.png`, `local-chess-256-verify.png`; asset `examples/assets/chess.glb` |
| STL → GLB | Green | Blender 5.1.1 `stl_import` → glTF export (`out/cube.glb`, 1396 bytes) | Not rendered | `tools/import-smoke/out/cube.glb` |
| STP / STEP | Green (CLI), viewer redirects | `convert_stp_to_glb.sh`: gmsh 4.15.2 → STL → Blender → GLB. `fixtures/box.step` → `out/box-stp.glb` (12,360 bytes, valid glTF header) | Only a generated 10 mm cube was tested, no real CAD part. gmsh came from a pip venv (`brew install` blocked). No unit conversion (mm vs m), no materials. Viewer shows a "convert first" toast; GLB not rendered. Remote relay path untested | `tools/import-smoke/out/box-stp.glb`, `fixtures/box.step` |
| FBX | Green (CLI), viewer redirects | `convert_fbx_to_glb.sh`: Blender `import_scene.fbx` → `export_scene.gltf`. `fixtures/sample.fbx` (533 KB) → `out/sample-fbx.glb` (486,928 bytes, 25 meshes, 10 materials) | GLB not rendered. Viewer shows a "convert first" toast; no in-browser FBX | `tools/import-smoke/out/sample-fbx.glb` |
| x_t, IGES (reference) | Out of scope | `stage-converter.py` marks `.x_t .igs .iges .stp .step` as Pixyz-only (Windows) and fails them on Linux | Pixyz license and Windows worker | same file |

## Viewer decision

`.fbx`, `.stp` and `.step` are recognized (file picker `accept`, drop hint, home page) but are not in `isModelFile`. On drop, `ViewerEngine.loadFiles` and the home page show a toast naming the `convert_*.sh` script instead of loading. Reason: no FBX or OpenCASCADE code in the browser bundle. Test: `viewer/tests/pbrt-loading.test.ts`.

## Open items

1. Render `out/sample-fbx.glb` and `out/box-stp.glb` with the viewer or `mutracer-render`.
2. Run a real (non-cube) STEP part; decide mm → m scaling.
3. Make `blender` resolvable for `tools/cloud-relay.py` on macOS (PATH or `BLENDER` variable), and add gmsh to the relay host.
4. Make `mutracer-render` defaults work for glTF Y-up scenes, or document `--camera-mode lookat` in the cloud-service README.
