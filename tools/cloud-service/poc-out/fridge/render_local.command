#!/bin/zsh
cd /Users/wangjianzheng/Project/git/mutracer
log=tools/cloud-service/poc-out/fridge/stage-fridge-local.log
png=tools/cloud-service/poc-out/fridge/stage-fridge-local.png
start=$(date +%s)
native/host/target/release/mutracer-render \
  --scene tools/cloud-service/poc-out/fridge/stage-fridge-scene_snapshot.json \
  --asset-map tools/cloud-service/poc-out/fridge/stage-fridge-assets.json \
  --out "$png" \
  --view 298cfe60-923d-44fb-a0d1-f2206b9a48e1 \
  --width 512 --height 512 --samples 32 --bounces 3 --denoise 1 --timeout-ms 600000
exit_code=$?
elapsed=$(( $(date +%s) - start ))
print "render_exit=$exit_code wall_seconds=$elapsed" > "$log"
if [[ $exit_code -eq 0 ]]; then
  file "$png" >> "$log"
  print 'LOCAL_RENDER_DONE' >> "$log"
fi
