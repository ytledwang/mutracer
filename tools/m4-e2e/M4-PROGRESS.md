# M4 主链最小串通：完成（本机多机位 + 云端成片均通）

## 一键

```bash
export BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
tools/m4-e2e/run_m4_demo.sh            # 本机；SKIP_M2=1 复用已有 M2 产物
tools/m4-e2e/run_m4_demo.sh --cloud    # 另提交云端（ssh 到 ubuntu@43.192.32.90）
```

末行 `DONE_M4 scene=… previews=… [cloud=…]`。可覆盖：`GLB GLB_KEY GLB_POS GLB_SCALE VIEWS HDRI_BRIGHTNESS EXPOSURE WIDTH HEIGHT SPP`。

## 步骤

1. 选模板：`tools/scene-template/run_m2_demo.sh`（冰箱厨房模板 + 单品 `1d0db88a-…`，`replace_id` 合并）→ `m2-preview-scene.json`。
2. 导入：`apply_thin_params.mjs` 把 `examples/assets/chess.glb`（可换 `import-smoke/out/sample-fbx.glb`、`box-stp.glb`）作为新 mesh/model 挂到 `model_root`，位置 `0.9,-1.2,0`、缩放 0.6，路径写入 `out/m4-assets.json`（key `m4/import.glb`）。
3. 薄调参（两项，均已确认 `stage_render.rs` 读取）：环境 `hdri_brightness` 0.8 → 1.2；相机 `post_processing_settings.exposure` 0.8 → 1.0。`run_dual_track.py preview` 不传 `--light-scale`，所以没用它。
4. 多机位：从单品 scene 取两个 view（`298cfe60-…` 正面、`3c697acc-…` 侧前），克隆合并 scene 的基础 view，换成对应产品相机，写入 `m4-scene.json`。再 `run_dual_track.py preview --views id1,id2`，640x360、16 spp，每张约 11.5 s。
5. 云端：`submit_cloud_ssh.sh` → scp scene、chess.glb、`remote_submit.py` → 远端 `source env` 后向 `127.0.0.1:8787` 提交 → poll → scp 回图。token 只在远端 shell 里，不落本机文件。远端资产取自已有 `/tmp/mutracer-fridge-assets`，chess 以 `m4/import.glb` 随 payload 带上。

## 产物（`tools/m4-e2e/out/`）

- `m4-preview-298cfe60.png`、`m4-preview-3c697acc.png`：两个机位，两张图平均像素差约 24/255，构图不同；已目视检查其中一张含冰箱与棋子。
- `m4-cloud.png` = `m4-cloud-43af5cb0.png`：云端 job `43af5cb0016a421f865a1b498fd009f9`，640x360、32 spp、view `298cfe60`，succeed，排队加渲染约 30 s，整体命令约 40 s。
- `m4-scene.json`、`m4-assets.json`：派生 scene 与 asset map（可复现）。

## EXIT 摘要

| 步骤 | 结果 |
| --- | --- |
| M2 复用 | 0 |
| apply_thin_params | 0 |
| 本机 preview ×2 | 0 |
| 云端 submit | 0（succeed） |

缺口见 `docs/technical/m4-e2e-gap.md`。未提交、未 push。
