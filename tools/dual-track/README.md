# Dual-track stage rendering

One stage JSON and one asset map drive both tracks:

```bash
python3 tools/dual-track/run_dual_track.py both \
  --scene tools/cloud-service/poc-out/fridge/stage-fridge-scene_snapshot.json \
  --asset-map tools/cloud-service/poc-out/fridge/stage-fridge-assets.json \
  --assets-root tools/cloud-service/poc-out/fridge/assets \
  --view 298cfe60-923d-44fb-a0d1-f2206b9a48e1 \
  --preview-out preview.png \
  --final-out final.png \
  --compare-out compare.png \
  --ref tools/cloud-service/poc-out/fridge/ref/fridge-ref-front-329c.png \
  --metrics-out metrics.json
```

- `preview` runs `mutracer-render` with the verified UE↔glTF semantics.
- `final` invokes headless Blender Cycles through `blender/run_blender_final.py`.
- `both` runs the selected tracks and, when `--compare-out` is given, creates a
  side-by-side image plus `arch-metrics.json`.

Blender material overrides use scene PBR values and linked maps; only CAD debug,
charcoal door edges, drawer pearl, and glass receive final-track special cases.

The asset map may be an object or `{key, value}` entries. Relative local paths are
resolved against `--assets-root` and then the map file. See
`docs/technical/dual-track-render.md` for the complete architecture and
`tools/dual-track/stage_semantics.md` for the shared scene conventions.


## Multi-view preview

```bash
python3 tools/dual-track/run_dual_track.py preview \
  --scene tools/cloud-service/poc-out/fridge/stage-fridge-scene_snapshot.json \
  --asset-map tools/cloud-service/poc-out/fridge/stage-fridge-assets.json \
  --views 298cfe60-923d-44fb-a0d1-f2206b9a48e1,3c697acc-1228-4e46-ba54-77eb7bb87cfb,da307f8c-a522-4ec9-a1fe-03f7092e1dfc \
  --preview-out tools/cloud-service/poc-out/noise-study/fridge-3views/preview.png
```

- `--view` one id (legacy). `--views` comma-separated. `--all-views` uses `render_settings.views_in_task` if present, else every key in `views`.
- Multi-view writes `preview-<view前8位>.png` (same for `--final-out` / metrics).
- Preview defaults: `--preview-spp 32`, `--preview-bounces 8`, `--denoise 1`. Pass `--oidn-library` through to `mutracer-render` (see `docs/technical/oidn-native.md`).
