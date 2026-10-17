# WorkState

轻量级工作活动状态记录工具。

按分钟记录程序活动，通过多种图表回顾电脑使用时间。数据保存在本机，支持 CSV 导出原始记录。

[项目主页](https://github.com/3plus10i/workstate) · [下载](https://github.com/3plus10i/workstate/releases) · [更新记录](CHANGELOG.md)

WorkState 从 **v4.0.0** 开始独立发布。项目前身：[PCState](https://github.com/3plus10i/pcstate)。

## 使用

需要 Windows 10/11 和 Microsoft Edge WebView2 Runtime。

解压 `WorkState-4.0.0-Windows.zip`，打开其中的 `WorkState/WorkState.exe`。发布包仅含单文件 EXE 和 README，EXE 可单独运行。

- 双击托盘图标打开窗口；关闭窗口后继续在托盘记录，从托盘菜单选择“退出”结束程序。
- 在“设置 → 记录设置”中开启开机启动，默认关闭，强烈建议开启。
- 需要保持程序运行才能记录；退出、休眠或暂停期间不补记。
- 可暂时中止记录一段时间，到时自动恢复，期间可以随时手动恢复。
- 想先体验图表界面效果，可通过 cmd 运行 `WorkState.exe --demo` 开启演示模式；演示模式不采集真实活动。
- 在“关于”中手动检查更新，下载后选择“重启并更新”；保留原有数据、设置及开机启动状态。

## 功能

- **时间报表**：单日和多日热力图、饼图、柱状图。图表只在修改查询条件或手动刷新时更新。
- **程序细分**：默认按程序汇总。对 IDE、Office软件及浏览器等`富内容程序`，可进一步按项目名、文档名、网站名进行细分。
- **可调整规则**：细分名单可修改，网站关键词可修改，可设置不记入的进程黑名单，可设置程序在图表中的显示名。
- **数据查看**：快捷查看近八小时的原始记录。更多数据可导出查看。
- **数据管理**：数据库长期保存；可手动预览并清理历史记录、导入 PCState 数据库、导出 CSV 格式原始记录数据。

默认支持的细分程序：

| 类型 | 默认进程 |
| --- | --- |
| IDE | Visual Studio Code、Cursor、PyCharm、IntelliJ IDEA |
| Office | Word、Excel、PowerPoint、OneNote |
| 浏览器 | Chrome、Edge、Firefox |

其他程序可在设置中添加进程名。细分依赖窗口标题，无法识别的内容仍按程序统计。细分项目有最低活动时间门槛，以免频繁打开项目或网页产生过多分类。网站关键词按长度降序匹配，较长关键词优先。

## 工作原理与数据隐私
程序在本地记录、分析和存储活动数据，不会上传用户活动数据。仅在用户主动检查或下载更新时访问 GitHub；连接失败时回退到 ghproxy，下载沿用查新选定的源。

每分钟判断刚过去一分钟的活动状态，闲置阈值固定为一分钟。记录包含进程名和窗口标题，不记录按键内容或屏幕图像，不上传活动数据。

新安装的数据默认位于 `%LOCALAPPDATA%/WorkState/data`，包含 `activity.sqlite3` 和 `workstate.log`。数据库永久保存，诊断日志保留一个自然月；不自动分割数据库或生成 CSV 归档。可通过 `--data-dir PATH` 指定目录。

进程黑名单中的程序不会被记录；支持 `//` 行内注释。CSV 包含原始窗口标题，可能含有网页标题、文档名等个人信息，分享前请检查。

清理历史记录按本机自然日 0:00 划分，不受报表的一天起始时间影响。操作前显示记录数，需要确认后才会永久删除。详见[数据管理说明](docs/data.md)。

## 从 PCState 迁移

如果您是旧版 PCState 用户，可以方便的将数据迁移到 WorkState。

1. 打开“设置 → 数据存储 → 导入旧版数据库”，选择 PCState 的 `pcstate.db`。
2. 检查日期范围、新增和重复记录数，确认导入。已有分钟记录保留，重复导入不会增加重复记录。
3. 导入完成后，**关闭旧版的开机自启，并从托盘退出旧版**，避免同时记录。

导入不会改动旧数据库，也不会覆盖本版设置。早期版本没有保留的原始进程名或窗口标题无法恢复。旧 CSV 归档不会自动读取。

若本机已有 `%LOCALAPPDATA%/PCState/data/activity.sqlite3`，且新目录尚无数据库，WorkState 会沿用该目录，保留已有记录与设置。这与导入旧版 `pcstate.db` 是两种情况。

## 开发与打包

使用 Python 3.11+、Node.js 22.18+。桌面界面由 pywebview / WebView2 加载本地页面，前端使用 TypeScript、React、Ant Design 和 ECharts；正式程序不启动本地 HTTP 服务。

在项目目录执行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Set-Location frontend
npm ci
npm test
npm run build
Set-Location ..
.\.venv\Scripts\python.exe main.py --demo
```

运行后端测试和生成 Windows 发布包：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build.py --skip-frontend --release
```

输出为 `release/WorkState/`、`release/WorkState-4.0.0-Windows.zip` 和 `release/SHA256SUMS.txt`。不传 `--skip-frontend` 时，打包脚本会先安装前端依赖、运行前端测试并重新构建；后端测试始终执行。

更多说明：[开发指南](docs/development.md) · [数据管理](docs/data.md) · [图标资源](docs/logo.md) · [发布规范](docs/releases.md)。
