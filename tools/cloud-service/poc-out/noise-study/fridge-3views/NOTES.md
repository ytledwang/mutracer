# Fridge 3-views + cloud verify 2026-11-09 Asia/Shanghai

## Local preview (32spp / 8 bounces / OIDN on)
Views from scene (no render_settings.views_in_task; used first 3 of 4 scene views):
- 298cfe60 Front: mean_abs 1.23 (ROI) — target ≤1.5 OK
- 3c697acc 新视图: 0.77 OK
- da307f8c 新视图: 0.37 OK

## Cloud ubuntu@43.192.32.90
- SSH: recovered after Mac left aTrust/utun7 (gateway was 198.18.0.1; now en1/192.168.0.1). Earlier hang was post-TCP banner exchange.
- Rebuilt mutracer-render with clang++-10; installed to /home/ubuntu/mutracer/bin/mutracer-render
- OIDN auto: /opt/blender/lib/libOpenImageDenoise.so
- Front 32spp b8: d0 mean_abs ~same class as local off; d1 denoise=on file 140550B vs d0 262312B
