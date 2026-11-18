# Material-faithful Blender run

- Replaced the non-charcoal clay overrides with scene-driven base color, metallic, and roughness.
- Linked basecolor, normal, and roughness texture inputs instead of muting basecolor.
- Removed the global roughness floor, bright-color crush, and glass gray clamp.
- Kept CAD debug plastic, charcoal door-edge powder coat, and the low-roughness glass path.
- Lifted matching refrigerator drawer faces to preview's near-white pearl `[0.96, 0.96, 0.955]`.
- Final rendered locally with Blender 5.1.1, Metal GPU, and 256 SPP. Preview completed successfully at 32 SPP.

## Result

- The final is no longer uniformly clay: pearl drawer fronts, charcoal outer door edges, transmissive glass, and metallic/lacquer interior response are visible.
- Remaining gap versus the gold: the Cycles final is brighter/whiter on the body and has interior placement/background differences that lower silhouette IoU; these are not material clay clamps.
- Metrics: preview IoU 0.7993, final IoU 0.3797, brightness standard deviation preview 43.968, final 44.052, reference 43.364.

## Cloud re-render

- Target: `ubuntu@43.192.32.90` headless `/usr/local/bin/blender`.
- Status: **blocked** from Mac mini at Asia/Shanghai 2026-11-09 ~21:50.
- TCP :22 and :8787 connect, ICMP blocked; SSH hangs at banner exchange (`Connection timed out during banner exchange`) after multiple retries (8–60s).
- No `cloud-final.png` produced this run. Local final at 256 SPP is the acceptance artifact.
- Next: restore SSH/banner path (host sshd or middlebox), then rsync `tools/dual-track` + fridge scene/assets and re-run final spp 256–512.
