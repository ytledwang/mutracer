# 汉化盘点：仍保留的英文及原因

时间：2026-11-11 Asia/Shanghai。只改了用户可见的 viewer 外壳文案，未改交互框架，未把 Living Room 等预设改成「场景模板」。三分法文案保持：实时查看 / 高质量预览 / 提交渲染。

## 专有名词（按要求保留）

GLB、glTF、FBX、STP / STEP、HDRI、AgX、Pivot、WebGPU、WebGL、OIDN、MaterialX、PBRT、URL、MuTracer。

## 仍为英文、及原因

| 位置 | 英文 | 原因 |
| --- | --- | --- |
| `DebugOverlay.tsx` | Interactive preview 等调试项 | 调试叠加层，不是日常外壳；且 `previewEnabled` 名称按 F2 约定不得与「实时查看」混用 |
| 渲染/材质面板字段 | roughness、metalness、BVH、spp 等 | 技术参数名，与引擎/文档一致 |
| 示例库条目 | Living Room 及其他预设名 | 禁止把 Living Room 预设改成场景模板；专有条目名保留 |
| 场景树节点名 | Front、BingXiang、room 等 | 来自 scene.json / 资产，不是 UI 外壳 |
| 顶部品牌 | MuTracer Viewer | 产品名 |
| 后端菜单 | WebGPU、WebGL 2、OIDN | 专有名词 |

检查：`viewer/tests/chromeI18n.test.ts`（`npm run test:viewer` 覆盖）。
