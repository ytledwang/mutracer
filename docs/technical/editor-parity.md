# Editor feature parity

MuTracer is a rendering library and viewer, not a scene editor. This note maps
MuTracer capabilities to the editor-side features in the my-stage project. It is
not a commitment that all editor features move into MuTracer. The editor should
continue to own scene identity, workflow, asset management and persistence;
MuTracer can own conversion, interactive rendering and offline rendering.

Use these categories:

- **Covered** — MuTracer has the rendering capability, though the host application
  still needs its own UI and persistence.
- **Partial** — MuTracer has the underlying capability, but not the complete
  editor workflow.
- **Missing** — the capability is absent or would require renderer work.
- **Separate** — better implemented by the host application rather than MuTracer.

## Result

MuTracer can replace the photorealistic rendering core, but not the editor. The
largest hard gaps are scene editing, decals, transform gizmos, production asset
management, persistent scene views and task-based cloud rendering. The largest
adapters are therefore scene conversion and a cloud worker, not a rewrite of the
editor UI.

| Area | my-stage editor | MuTracer | Parity |
| --- | --- | --- | --- |
| Scene model | Authoritative scene JSON with models, groups, lights, decals, cameras, environments, views and materials. | A rendering scene is meshes, analytic lights and optional background. The viewer builds a read-only Three.js-derived scene tree. | Partial |
| Scene editing | Add, delete, rename, group, reorder, lock, duplicate and copy/paste. | View meshes/lights/cameras, select, show/hide and edit materials; no editing scene hierarchy. | Separate, with optional host-side editing |
| Undo/redo | Command stacks for scene edits. | Viewer can undo material, visibility, lighting and render settings; there is no scene-graph command layer. | Partial |
| Object picking | UE Pixel Streaming returns raycast hits. | Viewer picking identifies meshes/materials and follows displacement and alpha cutout. | Covered |
| Transform gizmos | UE gizmo for move/rotate/scale. | None. | Missing |
| Box selection | UI exists in the editor; completion is limited. | No multi-object selection. The viewer's screen rectangle highlights the selected object. | Missing |
| Models/instancing | Scene JSON references GLB assets and UE instances. | GLTF/GLB import, shared geometry, rigid instances and skinned/morphed Three.js imports. | Covered |
| Materials | UE material schema, official/user materials, texture slots, binding mode and preview. | OpenPBR 1.1, standard/physical Three.js conversion, MaterialX import, texture slots and a material editor. | Covered for rendering |
| Material groups/variants | Material groups and active-child state participate in views. | Shared material edits exist, but no named material groups or variant sets. | Missing |
| Decals | Dedicated decal tree, placement and parameters. | No decal system. | Missing |
| Analytic lights | Directional, point, spot and area lights. | Directional, sphere, spot and rect lights. | Covered |
| Light details | IES, source textures, attenuation radius, barn doors and light channels. | Rect textures and spot IES profiles. Barn doors and distance falloff controls are absent. | Partial |
| Environment | HDRI, sun, brightness, contrast, angle and backplates. | HDRI, studio rigs, procedural sky, background/grounded skybox, intensity and rotation. | Covered for rendering |
| Environment sets | Named environment entities and views can switch them. | Background and lighting are scene/display settings, not a persisted environment entity system. | Separate |
| Camera | Camera entities, frame size, sensor/FOV, exposure and post processing. | Perspective/orthographic cameras, imported cameras, depth of field, autofocus and fixed-size export camera override. | Covered for rendering |
| Camera presets | Cameras are entities and views reference them. | Viewer can switch authored cameras and persist the local view, but has no server-side preset system. | Separate |
| Camera animation | Entity animations with a timeline and playback. | Imported glTF animation playback, but no camera-animation creation or keyframing. | Missing |
| Views | One view switches camera, environment, group visibility, lights and material variants. | URL settings and local saved preferences, but no named view presets or automatic group switching. | Missing or host-side |
| Materials in views | View restores material group state. | No material group state. | Missing |
| Rendering | UE Pixel Streaming for interactive view and render tasks for offline output. | WebGPU path tracing with WebGL 2 fallback, progressive preview, convergence, denoising, AOVs and PNG export. | Covered, different architecture |
| Denoising | Render task flag; UE handles it. | JNLM on both backends and OIDN on WebGPU. | Covered |
| AOVs | Render dialog requests normal, depth, object/material ID and base color. | Final/albedo/normal/depth/position/roughness/diffuse/specular/ID/motion, with object/instance/material/primitive ID lanes. | Covered |
| Animation output | Render tasks can produce frame sequences. | Frame rendering and animation playback exist; video encoding does not. Use frame output plus ffmpeg. | Partial |
| Caustics | Not an editor feature. | Experimental light tracing and photon mapping on WebGPU. | Covered |
| Assets | Supabase-backed official/user assets, categories, search, upload and preview. | Local/URL model loading, examples and texture/environment presets; no DAM. | Separate |
| Persistence | Scene JSON in Supabase plus autosave. | Link settings and browser-local preferences/cache; no scene storage. | Separate |
| Cloud rendering | Supabase render tasks consumed by UE/Blender workers. | No worker integration yet. A task adapter can invoke a native MuTracer worker. | Missing |

## Priorities

1. **Cloud still-render worker.** Convert the editor scene to a MuTracer scene,
   render with native/WebGPU on a GPU worker and return progress and images. This
   is required to prove the production chain and does not change the editor data
   model.
2. **Scene adapter.** Provide a lossy first pass for GLB-driven models and
   authored cameras/lights; defer editor-only concepts that do not affect a
   still render.
3. **Decals.** Only if they must appear in offline output. This is a renderer
   feature, not merely an adapter.
4. **Transform gizmos.** Best implemented in the host viewer/editor, with the
   renderer receiving updated transforms. Do not build a shared runtime scene
   decision layer.
5. **View presets and material variants.** Persist them in the host scene model
   and translate the active view to MuTracer settings when rendering.
6. **Camera animation/video.** Use frame sequences and ffmpeg first; decide
   whether interactive keyframing belongs to the host editor or a later tool.

## Adapter boundaries

Do not make MuTracer the scene-graph authority. The host keeps the scene tree,
asset IDs, undo history and persistence. A converter should map one committed
scene snapshot to MuTracer inputs and report unsupported nodes explicitly. The
cloud worker should accept a render task, download assets, convert, render,
write progress and return files using the existing task protocol. Interactive
cloud preview is a later concern because it needs a different transport and
session lifecycle.
