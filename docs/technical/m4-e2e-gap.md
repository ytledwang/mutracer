# M4 主链缺口清单

范围：模板 → 导入 → 薄参 → 多机位预览 → 云端成片。复现入口见 `tools/m4-e2e/M4-PROGRESS.md`。

## 今晚已知

1. 转换后的 GLB 未在浏览器里实际打开。`sample-fbx.glb`、`box-stp.glb` 只检查过 glTF 头和 JSON。M4 只把 chess.glb 渲过（本机和云端）。
2. STP 转换没有单位也没有材质。gmsh 输出不做 mm → m 缩放，GLB 无材质；测试件是生成的立方体，不是真实 CAD。
3. 厨房 GLB 缺。模板 mesh（`official_asset/template/RF_Scene_Kitchen_2cam/…`，55 个）不在本地备份，预览 scene 把 87 个节点设为不可见并清空 35 处贴图引用，所以 M4 预览里只有冰箱和导入物，没有厨房。云端 payload 用同一份 asset 集合，云端图同样没有厨房（未单独核对远端 `official_asset` 内容）。
4. 模板相机和面板仍是 sample。模板 `cam_01` 朝向与冰箱不符；`SceneTemplatePanel` 列表仍读 `scene-templates.sample.json`，viewer 不执行合并。
5. x_t / PiXYZ 不做。

## 新发现

6. 合并 scene 只有 1 个 view（`1c4a3883-…`，用模板相机）。M4 用 `apply_thin_params.mjs` 把产品 scene 的 view 克隆进来，是预览派生物，不在 `m2-merged.json` 里。合并脚本应把产品 views 一并带入并 remap。
7. 合并后各 view 的 `model_group_visibility` 不含导入的新模型，脚本手工补 `true`。合并 README 里已列 `model_group_visibility` 不 remap，同一问题。
8. 导入还没有产品化入口：GLB 以手写 mesh/model 节点加入，位置和缩放靠环境变量猜（chess 0.6 倍，位置 0.9,-1.2,0）；没有按包围盒自动落地、对齐地面或摆放的逻辑。`sample-fbx.glb` 首个 accessor 的包围盒约 ±400 单位，疑似厘米量级，直接引用大概需要缩放约 0.01（未实测），M4 默认没引用它。导入物无材质覆盖。
9. 薄参只验证了 `hdri_brightness` 与相机 `exposure`（`stage_render.rs` 读取两者）。`run_dual_track.py preview` 不把 `--light-scale` 等参数传给 `mutracer-render`，这些只作用于 Blender final 轨。云端 worker 只透传 `light_scale`、`view`、`samples` 等，没有 hdri 参数，所以云端薄参必须写进 scene。
10. 云端 payload 体积：scene + 442 个 base64 资产约 207 MB，一次 POST 走 SSH 内网可用，公网 8787 或浏览器直传不现实。需要按 hash 去重/预上传，或让 worker 从远端资产目录按 key 解析。当前 `remote_submit.py` 依赖远端已有 `/tmp/mutracer-fridge-assets`（只在远端临时目录，重启即丢）。
11. 云端图与本机图不逐像素一致（云端 32 spp，本机 16 spp，视角相同的 `298cfe60` 平均像素差约 1.2/255）；未做更严格的数值对比。
12. 公网 :8787 未测（按要求走 SSH 内网）。`/healthz` 无 token 返回 401 属正常。
13. 云端认证：API token 在远端 `env`，没有按用户/租户的鉴权或配额；`submit_cloud_ssh.sh` 依赖本机已有 SSH 免密。
14. 远端 `/tmp/m4-scene.json`、`/tmp/chess.glb`、`/tmp/remote_submit.py`、`/tmp/m4-cloud.png` 未清理。

## 复现云端

```bash
tools/m4-e2e/run_m4_demo.sh --cloud       # 或单独：tools/m4-e2e/submit_cloud_ssh.sh（需 out/m4-scene.json）
ssh ubuntu@43.192.32.90 'systemctl is-active mutracer-cloud-api mutracer-cloud-worker'
```
