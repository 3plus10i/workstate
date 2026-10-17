# WorkState 开发与发布约定

- 保持轻量、清晰的桌面界面；说明文字使用次要样式，不添加装饰性副标题。
- 活动记录和设置属于用户数据，更新程序不得覆盖、重建或移动数据目录。
- 网络仅用于用户主动检查和下载更新：优先 GitHub，连接失败或超时后回退到 `https://gh-proxy.org/`；附件和校验文件沿用此次查新选定的源。
- 发布前必须同步版本号、编写对应版本的 CHANGELOG，并运行元数据检查、前后端测试及构建。使用 `python tools/release.py set-version x.y.z` 更新版本，不手改锁文件中的依赖版本。
- Git 标签必须是 `vX.Y.Z`，与程序版本完全一致。每次正式发布必须有更新说明和两个附件：`WorkState-X.Y.Z-Windows.zip`、`SHA256SUMS.txt`。
- ZIP 内严格只有 `WorkState/WorkState.exe` 和 `WorkState/README.md`；更新器依赖此约定。
- 优先通过 `.github/workflows/release.yml` 发布。先创建完整草稿，再公开，禁止覆盖已发布版本的附件。步骤见 `docs/releases.md`。
- 演示、测试和截图使用虚构数据。不得把数据库、导出、日志、依赖目录或构建产物提交到 Git。
