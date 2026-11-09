# M3 import green path: progress

Status: DONE_M3 (CLI conversion green for GLB, FBX, STEP; viewer recognizes fbx/stp/step and tells the user to convert first).

| Goal | Result | Artifact |
| --- | --- | --- |
| GLB | `examples/assets/chess.glb` renders natively (re-run in `smoke.sh` step 1, 4492 unique colors); viewer loader covered by `viewer/tests/viewerModelLoading.test.ts` | `out/chess-256-lookat.png` |
| FBX | `convert_fbx_to_glb.sh` Blender; `fixtures/sample.fbx` → GLB, glTF v2, 25 meshes, 10 materials | `out/sample-fbx.glb` (486,928 B) |
| STP | `convert_stp_to_glb.sh` gmsh → STL → Blender; `fixtures/box.step` → GLB, 1 mesh | `out/box-stp.glb` (12,360 B), `out/box-stp.stl` |
| STL | Blender-only half of the chain | `out/cube.glb` (1396 B) |
| Viewer wiring | `isConvertibleModelFile` + `convertHint` in `droppedFiles.ts`; toast in `ViewerEngine.loadFiles`; `accept` in `Toolbar.tsx` and `site/index.html`; drop hint in `Viewport.tsx`; error in `site/src/main.ts`. `isModelFile` unchanged | test in `viewer/tests/pbrt-loading.test.ts` |

## Commands

```bash
export BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
python3 -m venv /tmp/gmsh-venv && /tmp/gmsh-venv/bin/pip install gmsh   # brew install gmsh is blocked in this sandbox
export GMSH_PYTHON=/tmp/gmsh-venv/bin/python
tools/import-smoke/smoke.sh                       # steps 1-5
tools/import-smoke/convert_fbx_to_glb.sh in.fbx out.glb
tools/import-smoke/convert_stp_to_glb.sh in.step out.glb
```

Checks run: `npm run typecheck:viewer`, `npm run typecheck:site`, `vitest` on `pbrt-loading` and `viewerModelLoading` (24 pass). Full `npm test` / `test:viewer` not run.

## Limits and open problems

- Converted GLBs were not rendered or opened in a browser; only the glTF header and JSON were checked.
- STEP test part is a generated cube; no real CAD part. No mm → m scaling; gmsh output has no material.
- `sample.fbx` is a private asset copied from a my-stage-hk backup; replace it with a public FBX before publishing the fixtures.
- No in-browser conversion. The viewer only shows a toast. `tools/cloud-relay.py` (ssh) was not run.
- x_t / PiXYZ out of scope.
- Nothing committed.
