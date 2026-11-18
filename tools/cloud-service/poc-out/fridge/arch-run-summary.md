# Fridge dual-track architecture run

## Result

- Preview: `tools/cloud-service/poc-out/fridge/stage-fridge-arch-preview.png`
- Final: `tools/cloud-service/poc-out/fridge/stage-fridge-arch-final.png`
- Comparison: `tools/cloud-service/poc-out/fridge/arch-vs-ref.png`
- Metrics: `tools/cloud-service/poc-out/fridge/arch-metrics.json`
- Acceptance: **met**; `silhouette_iou_final_vs_ref` is `0.86081`, above the
  `0.7` target and the fallback threshold of `0.5`.
- Final corner RGB: top-left `(255, 255, 255)`, top-right `(255, 253, 254)`,
  bottom-left `(253, 252, 253)`, bottom-right `(255, 254, 254)`.
- Reference corner RGB: all four corners `(255, 255, 255)`.
- Comparison background color: final RGB `(255, 253, 254)`,
  reference RGB `(255, 255, 255)`, from the corner-median used by the comparison.
- Mask areas on the native image sizes: final `148342`, reference `145741`.

## Camera

The stage `fov` is the horizontal angle. Blender now uses
`sensor_fit: HORIZONTAL` and computes `lens` from `sensor_width`, so the final
track matches the stage renderer's horizontal field of view. The camera matrix
is unchanged.

## Overrides

The white environment uses pure white color and Strength `1.0` under
`view_transform: Standard`. Material colors with `sum(color) / 3 > 0.65` are
replaced by `(0.55, 0.55, 0.55)`. The charcoal overrides for sheet-metal powder
coating and `door_edge_meshes` are retained.

Non-charcoal materials are forced to `metalness: 0.0` and `roughness >= 0.45`,
including their roughness maps. Glass uses Transmission `0.0` and the
non-charcoal gray color. Charcoal door-edge materials retain `metalness: 0.12`.

## Metrics

```json
{
  "brightness_std": {
    "preview": 43.9345634957806,
    "final": 49.81821101401523,
    "ref": 42.81089388887461
  },
  "silhouette_iou_preview_vs_ref": 0.8004316040881151,
  "silhouette_iou_final_vs_ref": 0.8608100365620994,
  "threshold": 16
}
```

## Command

```bash
python3 tools/dual-track/run_dual_track.py both \
  --scene tools/cloud-service/poc-out/fridge/stage-fridge-scene_snapshot.json \
  --asset-map tools/cloud-service/poc-out/fridge/stage-fridge-assets.json \
  --assets-root tools/cloud-service/poc-out/fridge/assets \
  --view 298cfe60-923d-44fb-a0d1-f2206b9a48e1 \
  --preview-out tools/cloud-service/poc-out/fridge/stage-fridge-arch-preview.png \
  --final-out tools/cloud-service/poc-out/fridge/stage-fridge-arch-final.png \
  --compare-out tools/cloud-service/poc-out/fridge/arch-vs-ref.png \
  --ref tools/cloud-service/poc-out/fridge/ref/fridge-ref-front-329c-1024.png \
  --metrics-out tools/cloud-service/poc-out/fridge/arch-metrics.json \
  --preview-width 960 --preview-height 540 --preview-spp 32 \
  --final-width 960 --final-height 540 --final-spp 64 \
  --blender /Applications/Blender.app/Contents/MacOS/Blender
```


## Cloud

Remote headless Blender `/usr/local/bin/blender` at `ubuntu@43.192.32.90:/tmp/mutracer-final/` re-ran with the FOV-fixed `blender_inner.py`. Output: `tools/cloud-service/poc-out/fridge/stage-fridge-arch-final-cloud.png`.

Cloud IoU vs ref: `0.86129` (local final `0.86081`).
