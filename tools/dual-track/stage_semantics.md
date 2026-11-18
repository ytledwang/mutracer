# Stage scene semantics

- A stage scene is UE-like Z-up. Its model transforms use degrees in
  `rotation_euler`; material IDs are selected per mesh in `scene.materials`.
- `native/host/src/bin/stage_render.rs` is the preview-track implementation. It
  converts imported glTF geometry and cameras from glTF Y-up to stage UE Z-up as
  `(-z, x, y)`, normalizes the camera matrix last row, and lets scene materials
  override the mesh materials.
- The Blender final track uses `tools/dual-track/blender/blender_inner.py`. It
  consumes the same scene and asset-map semantics. Blender's glTF importer
  bakes Y-up vertices into Z-up with `RotX(+90)` and leaves the object matrix
  as identity. Since imported vertices are therefore already baked, apply
  `inv(RotX(+90))` after the preview-track glTF-to-UE basis. A model root is
  `sanitize(swap_yz @ ue_local @ gltf_to_ue @ inv(RotX(+90)))`; cameras keep
  `swap_yz @ ue_local_without_scale @ ue_basis_from_view`.
- `hdri_brightness` is passed directly to Cycles Background Strength.
- Blender material overrides pass scene base color, metallic, roughness, and
  linked basecolor/normal/roughness textures through instead of applying clay
  clamps. CAD debug names become white plastic; door-edge powder coat becomes
  charcoal; refrigerator drawer faces become near-white pearl; glass masters use
  transmission and scene glass roughness. Geometry, camera, FOV, light, and HDRI
  semantics are unchanged.
- TODO: extract the preview conversion into a reusable library crate so the
  final track can share validation without coupling Blender to Rust.
