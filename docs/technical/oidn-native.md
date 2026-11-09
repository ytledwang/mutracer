# OIDN in `mutracer-render` (stage_render)

`mutracer-render --denoise 1` (the default) denoises the converged HDR image with
Open Image Denoise. The binary does not bundle OIDN, so it locates a
`libOpenImageDenoise` shared library at run time.

## Lookup order

The first match wins:

1. `--oidn-library <path>`
2. `MUTRACER_OIDN_LIBRARY`
3. Auto-detection, first existing file of:
   - macOS: `<exe_dir>/../Frameworks/libOpenImageDenoise.2.dylib`,
     `<exe_dir>/../Frameworks/libOpenImageDenoise.dylib`,
     `<exe_dir>/libOpenImageDenoise.2.dylib`, `<exe_dir>/libOpenImageDenoise.dylib`,
     `/Applications/Blender.app/Contents/Resources/lib/libOpenImageDenoise.dylib`
   - Linux: `<exe_dir>/libOpenImageDenoise.so.2`, `<exe_dir>/../lib/libOpenImageDenoise.so.2`,
     `/usr/local/lib/libOpenImageDenoise.so.2`,
     `/usr/lib/x86_64-linux-gnu/libOpenImageDenoise.so.2`, then
     `/usr/local/blender*/lib/libOpenImageDenoise.so*` and
     `/opt/blender*/lib/libOpenImageDenoise.so*`

An explicit path from 1 or 2 that does not exist is an error for denoising, not a
reason to fall through to auto-detection.

## Output

- Found: stderr prints `oidn: <path> (<source>)`.
- Not found: stderr prints `warning: denoising disabled, rendering without it: <reason>`
  and the image is rendered without denoising. The render still succeeds.
- The last stdout line ends with `denoise=on`, `denoise=off(--denoise 0)` or
  `denoise=off(<reason>)`, so callers can tell whether the image was denoised.

## Setups

- macOS: Blender's own library is picked up automatically when Blender is installed
  in `/Applications`. Other locations: pass `--oidn-library` or set
  `MUTRACER_OIDN_LIBRARY`.
- Linux cloud: install OIDN 2.x so `libOpenImageDenoise.so.2` is on one of the paths
  above, put it next to the binary, or point at it explicitly:

  ```bash
  mutracer-render ... --denoise 1 --oidn-library /opt/oidn/lib/libOpenImageDenoise.so.2
  # or
  MUTRACER_OIDN_LIBRARY=/opt/oidn/lib/libOpenImageDenoise.so.2 mutracer-render ...
  ```

  The OIDN device libraries (`libOpenImageDenoise_device_*.so`, `_core`) must sit in
  the same directory as the main library. Backend selection is the default
  (GPU Metal/CUDA/HIP, then CPU).

## Check

32 spp, 8 bounces, 960x540 fridge view, crop `330,0,640,300`: `mean_abs` noise 7.55
without denoising and 1.23 with it.
