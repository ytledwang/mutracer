# r2 保真对照：官方内容拉取受阻（2026-11-11，Asia/Shanghai）

只读 GET，按明确路径 `official_asset/template/RF_Kitchen_0302_Scene/scene.json` 探测（未列桶、未碰 customer_asset、未写入任何东西）：

| 环境文件 | 主机 | 结果 |
|---|---|---|
| my-stage-hk `.env.production` | costage-supabase.haier.net:8443 | `URLError … [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol`；curl 同样 `LibreSSL SSL_connect: SSL_ERROR_SYSCALL`（rc=35） |
| my-stage-hk `.env.local` | supabase.sikishen.net:8000 | Python（走系统代理）`HTTP 502`；curl 直连 25s 超时 0 字节（rc=28） |

两个域名都解析到 198.18.0.x（本机系统代理 127.0.0.1 的 fake-IP TUN），上游到不了：haier.net 像是内网域名，需要公司 VPN 或内网出口。按"遇错即停"，没有绕路。

因此：官方壳 scene.json / GLB / 约 105 张贴图 / 灯光 / HDRI（含 White.exr 体积核查）/ 1.0 金样材质 **都没拉到**，计数 0、总量 0 B；Step 2 的"官方灯光 + 材质"Standard 重渲 **没有做**。
`bash tools/fusion-checks/official_pull_check.sh` 退出码 1（manifest 不存在），密钥扫描三项 PASS。
`bash tools/fusion-checks/fidelity_check.sh docs/prd/evidence/fusion/fidelity/r2` 退出码 1（没有 r2 渲染）。

Step 3（实时 vs 成片对齐）不依赖官方内容，已按本机 M2（c83a2f4a）做完，见 `align/`。
