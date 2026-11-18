#!/bin/zsh
cd /Users/wangjianzheng/Project/git/mutracer
ssh -o ConnectTimeout=15 -o BatchMode=yes ubuntu@43.192.32.90 \
  'printf "files="; find /tmp/mutracer-fridge-assets -type f | wc -l; printf "glb="; find /tmp/mutracer-fridge-assets -type f -name "*.glb" | wc -l' \
  > tools/cloud-service/poc-out/fridge/cloud-check.log 2>&1
printf "ssh_exit=$?\n" >> tools/cloud-service/poc-out/fridge/cloud-check.log
