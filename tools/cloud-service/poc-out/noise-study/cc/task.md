你在 /Users/wangjianzheng/Project/git/mutracer 仓库工作。只做下列两件事，完成后用中文简报：改了哪些文件、构建命令、验证输出。
硬约束：
- 绝对不要修改 tools/dual-track/blender/blender_inner.py（另一个 worker 在改）。
- 不要 git switch / checkout / commit / push / stash，不要动 HEAD（另一个 worker 在同一工作树上，提交由调度方另行处理）。
- 不要修改 native/host/src/ 下除 bin/stage_render.rs 以外的文件。

任务 A：native/host/src/bin/stage_render.rs
1. 第 ~1258 行 `render.set_denoiser(Default::default())` 实际传入 None（=关闭降噪）。改为传 Some(DenoiserOptions{ library: <探测结果>, ..Default::default() })。
2. OIDN 库探测（仅当 MUTRACER_OIDN_LIBRARY 未设置时）：按顺序找第一个存在的文件：
   exe_dir/../Frameworks/libOpenImageDenoise.2.dylib, exe_dir/../Frameworks/libOpenImageDenoise.dylib,
   exe_dir/libOpenImageDenoise.2.dylib, exe_dir/libOpenImageDenoise.dylib,
   /Applications/Blender.app/Contents/Resources/lib/libOpenImageDenoise.dylib (macOS);
   exe_dir/libOpenImageDenoise.so.2, exe_dir/../lib/libOpenImageDenoise.so.2, /usr/local/lib/libOpenImageDenoise.so.2,
   /usr/lib/x86_64-linux-gnu/libOpenImageDenoise.so.2, 以及 /usr/local/blender*/lib/libOpenImageDenoise.so* 和 /opt/blender*/lib/libOpenImageDenoise.so*（glob）(Linux)。
   设了环境变量就用环境变量。找不到时：--denoise 1 应打印清晰 stderr 警告并继续以不降噪出图（不要静默），并在 stdout 最后一行 "rendered ..." 里追加 denoise=on/off(reason)。找到时打印 "oidn: <path>" 到 stderr。
3. 新增 --oidn-library <path> 参数（优先级最高）。
4. 构建：cd /Users/wangjianzheng/Project/git/mutracer && MUTRACER_AOT_ARCHIVE=$PWD/.native-build/scene-core/render-core.lib.a CARGO_TARGET_DIR=$PWD/native/host/target cargo build --locked --release --manifest-path native/host/Cargo.toml --bin mutracer-render
5. 验证（不设环境变量）：用 tools/cloud-service/poc-out/fridge/stage-fridge-scene_snapshot.json + stage-fridge-assets.json，--view 298cfe60-923d-44fb-a0d1-f2206b9a48e1 --width 960 --height 540 --samples 32 --bounces 8，分别 --denoise 0 / 1 输出到 tools/cloud-service/poc-out/noise-study/cc/d0.png d1.png，用 python3 tools/cloud-service/poc-out/noise-study/noise_metric.py --crop 330,0,640,300 d0.png d1.png 报数，并报两图平均像素差（d1 应明显低噪，mean_abs 约 1.2）。
6. 新建文档 docs/technical/oidn-native.md：说明 stage_render 的 OIDN 查找顺序、--oidn-library、MUTRACER_OIDN_LIBRARY，Mac 用 Blender 自带库，Linux 云端如何指定。

任务 B：tools/dual-track/run_dual_track.py（只改这个文件和 tools/dual-track/README.md）
1. 新增 --views（逗号分隔 view id 列表）和 --all-views（从 --scene 的 views 字典取全部 view id；若 scene 文件里有 render_settings.views_in_task 则优先用它，元素可能是 {"id":..,"resolution":[w,h]} 或字符串）。保留原 --view 兼容。
2. 多视角时对每个 view 循环出预览（mode preview 或 both 中的 preview 部分；final 部分也按 view 循环），输出文件名在 --preview-out / --final-out 的 stem 后追加 -<view前8位>，例如 preview.png → preview-298cfe60.png。单视角时文件名保持不变。
3. 预览默认改为 --preview-spp 32、新增 --preview-bounces 默认 8（替换硬编码的 "3"）、--denoise 默认 1；新增 --oidn-library 透传给预览二进制。
4. 多视角时 compare/metrics 可跳过或按视角各自生成（metrics 文件名同样追加后缀）；不要破坏单视角原行为。
5. 跑一次：python3 tools/dual-track/run_dual_track.py preview --scene tools/cloud-service/poc-out/fridge/stage-fridge-scene_snapshot.json --asset-map tools/cloud-service/poc-out/fridge/stage-fridge-assets.json --all-views --preview-out tools/cloud-service/poc-out/noise-study/cc/mv/preview.png ，报告生成了哪些文件。
