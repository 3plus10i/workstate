# 图标资源

四柱标志以 SVG 为母版，圆角方形使用界面蓝 `#1677FF`，柱条为白色；闲置和暂停使用灰色 `#8C8C8C`。四柱包围框的中心与 256 × 256 画布中心重合。

| 资源 | 用途 |
| --- | --- |
| `public/workstate.svg`、`public/workstate-idle.svg` | 矢量母版 |
| `public/workstate.png`、`public/workstate-idle.png` | 512px 位图 |
| `public/workstate.ico`、`public/icon_active.ico`、`public/icon_idle.ico` | Windows 窗口及托盘图标 |
| `frontend/public/icon_active.ico` | 前端图标副本 |

ICO 包含 16、20、24、32、40、48、64、128、256px 图层。前端 HTML 内嵌 32px PNG favicon。

`tools/export_icons.cjs` 使用开发工具 Sharp 从 SVG 导出位图，并同步前端图标。运行 `node tools/export_icons.cjs`，或通过第二个参数传入可用的 Sharp 模块路径。Sharp 仅用于修改图标后的重新导出，不是应用或常规构建的必需依赖。
