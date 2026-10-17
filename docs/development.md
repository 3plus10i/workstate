# 开发指南

## 环境

- Windows 10/11，Microsoft Edge WebView2 Runtime。
- Python 3.11+，Node.js 22.18+。
- Python 运行依赖锁定在 `requirements.lock.txt`；前端依赖锁定在 `frontend/package-lock.json`。

按 [README](../README.md#开发与打包) 安装依赖并构建前端。`requirements.txt` 列出直接运行依赖；发布验证使用完整锁定文件。PyInstaller 为独立构建依赖，不随应用运行。

## 调试

建议使用演示数据，避免真实窗口标题进入截图、测试产物或仓库。

```powershell
.\.venv\Scripts\python.exe main.py --demo --data-dir .runtime/desktop
```

需要浏览器预览时：

```powershell
.\.venv\Scripts\python.exe main.py --preview --demo --data-dir .runtime/preview
# http://127.0.0.1:21521
```

修改前端后，在 `frontend` 目录运行 `npm run build`，再刷新预览页面。正式桌面程序加载本地 HTML，通过 pywebview 桥通信，不需要此服务。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
Set-Location frontend
npm test
npm run build
Set-Location ..
```

后端测试覆盖采集边界、统计和细分、设置、持久化、日期清理、CSV、旧库导入、日志及开机启动；前端测试覆盖日期区间、图表数据和悬停样式、暂停状态。

构建发布包后可运行原生自检：

```powershell
.\release\WorkState\WorkState.exe --demo --smoke-test --data-dir .runtime/smoke
```

自检启动真实 WebView2 窗口，检查页面、图表、通信和托盘，再自动退出；结果位于 `.runtime/smoke/demo/smoke-result.json`。该自检不替代长期后台运行测试。

## 发布

使用 `python tools/release.py set-version x.y.z` 同步程序、Python 元数据、前端和锁文件中的应用版本，前端离线显示直接读取包版本。随后编写对应版本的 CHANGELOG，执行 `python tools/release.py check` 并运行测试及构建。发布约定与 GitHub 工作流见[发布规范](releases.md)。

`python build.py --release` 会安装前端依赖、测试并构建前端、运行后端测试，生成 Windows 文件夹、ZIP 和 SHA-256 校验文件。已完成前端验证时可加 `--skip-frontend`；可用 `--dist-dir release/4.0.0` 改变解包目录，ZIP 仍输出到 `release`。

发布目录和 ZIP 内仅包含 `WorkState.exe`、`README.md`。EXE 使用单文件打包，运行依赖会在启动时解压到系统临时目录，退出后清理。面向用户的 README 来自 `docs/release-readme.md`；开发文档及更新记录保留在仓库。

仓库不包含数据库、CSV 导出、日志、依赖环境和构建结果。新建测试数据应使用虚构内容。

## 代码结构

| 路径 | 职责 |
| --- | --- |
| `workstate/collector.py` | Windows 前台活动采集与分钟循环 |
| `workstate/classification.py` | 程序及有限的标题识别规则 |
| `workstate/report.py` | 统计日、细分门槛与报表聚合 |
| `workstate/storage.py` | SQLite、历史清理与 CSV 导出 |
| `workstate/legacy.py` | 旧版数据库快照、检查与导入 |
| `workstate/service.py` | 前端共用接口 |
| `workstate/desktop.py` | 窗口、托盘、单实例与开机启动 |
| `workstate/preview.py` | 仅开发时使用的本机预览服务 |
| `workstate/logs.py` | 诊断日志轮换与保留 |
| `frontend/src/components/` | 页面、设置和图表组件 |
| `public/`、`tools/` | 图标母版、位图和导出工具 |
| `tests/`、`frontend/tests/` | 后端与前端测试 |
