# 发布规范

应用内更新依赖 GitHub Releases 的正式版本。保持此约定，后续版本才能被正确识别和安装。

## 首次发布 v4.0.0

v4.0.0 是 WorkState 的首个正式版本，开发期间的试验版本不作为发布历史。确认本地提交和 `v4.0.0` 标签就绪后，推送分支与标签：

```powershell
git push -u origin main
git push origin v4.0.0
```

推送标签会触发发布工作流。构建产物由工作流生成，不提交到源码仓库。确认工作流成功，并检查 Release 的更新说明、ZIP 和校验文件。

## 每个版本必须完成

1. 后续版本用 `python tools/release.py set-version 4.0.1` 同步程序、Python 元数据、前端及锁文件的应用版本。正式发布后不再修改同一版本的文件。
2. 在 `CHANGELOG.md` 顶部新增 `## [4.0.1] - YYYY-MM-DD`，填写面向用户的真实变更。这一节自动作为 Release 更新说明。
3. 执行 `python tools/release.py check`，运行测试及构建。验证后的变更需要先提交并推送到仓库。
4. 创建并推送与程序版本一致的标签，例如 `git tag v4.0.1`、`git push origin v4.0.1`。
5. Release 工作流会校验版本和标签，测试并构建，上传完整附件到草稿后公开为最新正式版。查看工作流结果并确认 Release 内容齐全。

工作流也可手动指定已存在的版本标签执行。已有 Release 时会停止，避免静默覆盖已发布内容。

## 固定内容

| 内容 | 约定 |
| --- | --- |
| 标签 | `vX.Y.Z`，仅正式的三个整数版本 |
| 标题 | `WorkState X.Y.Z` |
| 更新说明 | `CHANGELOG.md` 对应版本的内容，不使用自动生成的提交列表代替 |
| 发布包 | `WorkState-X.Y.Z-Windows.zip` |
| 校验文件 | `SHA256SUMS.txt`，包含本次发布包的 SHA-256 |
| ZIP 内容 | `WorkState/WorkState.exe`、`WorkState/README.md`，仅两项 |

GitHub 自动附带的源代码压缩包不属于安装包。草稿、预发布版以及同版本或更旧版本不会被应用当作可安装更新。

## 手动构建

```powershell
python -m pip install -r requirements-build.txt
python build.py --release
python tools/release.py check-package release/WorkState-4.0.0-Windows.zip
python tools/release.py notes --output build/release-notes.md
```

需要手动创建 Release 时，先建草稿，填写正确标签、标题及生成的更新说明，上传 ZIP 和校验文件后再公开。发布前也必须执行同样的检查。

## 更新行为

“关于 → 检查更新”首先请求 GitHub。超时、连接错误、限流或服务器暂时故障时，回退到 `https://gh-proxy.org/`。尚无正式 Release（404）不作为网络错误回退。查新选定后，校验文件和发布包始终使用同一个源。

下载完成后检查大小、SHA-256、ZIP 内容和 Windows 程序头。用户选择“重启并更新”后，独立更新进程等待主程序及 PyInstaller 启动进程退出，在原路径替换 EXE。新程序界面与数据库接口正常启动后才确认成功并清理备份；失败时恢复原 EXE。

程序沿用原数据目录和自启路径，不修改数据库、设置或开机启动选项。当前更新不涉及数据库结构变更；将来如需变更结构，必须另行设计兼容与备份策略。

镜像源是第三方转发服务；SHA-256 用于校验下载完整性，不替代代码签名。
