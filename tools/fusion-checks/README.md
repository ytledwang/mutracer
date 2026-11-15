# F2 / 主链可编程验收

新证据一律写到 `docs/prd/evidence/fusion/f2/r2/` 与 `docs/prd/evidence/fusion/demo/`，**不要覆盖**昨晚的 `f2-*-after-template.png` 等失败图。

```bash
cd /Users/wangjianzheng/Project/git/mutracer
# 一条入口：typecheck / unit / 图像与模式切换验收。任一步失败则总退出码非 0，单项仍全部记录。
bash tools/fusion-checks/f2_check.sh
```

`f2_check.sh` 会拉起（或复用）`127.0.0.1:3012` 的 viewer，并用本机 **headed Chrome + ANGLE Metal** 跑 `f2_check.mjs`。不要用失败截图自称通过。

主链 demo（仅在 F2 全绿后）：

```bash
bash tools/fusion-checks/demo.sh
```
