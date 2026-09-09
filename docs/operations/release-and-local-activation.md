# 发布与本地更新

Scientific Figure Builder 将发布、本地激活和宿主重载分开处理，但日常入口保持简单。
架构原因和安全边界见
[ADR-0011](../adr/0011-separate-release-activation-and-host-reload.md)。

## 普通用户

首次安装完整 Codex 集成：

```bash
./install.sh --codex --release latest --with-gui
```

以后更新已经安装的组件：

```bash
scientific-figure update --latest
```

检查本机状态：

```bash
scientific-figure status
```

`update` 默认保持当前安装形态。已经安装 Configuration app 就继续更新，没有安装就不会新增；
也可以显式使用 `--with-gui`、`--without-gui`、`--codex` 或 `--runtime-only`。

正式更新从 GitHub Release 下载完整 Product bundle，先验证 `SHA256SUMS`、Release
manifest 和内部文件摘要，再安装。离线时使用：

```bash
scientific-figure update --bundle ./scientific-figure-builder-X.Y.Z.tar.gz
```

离线 bundle 必须与 Release workflow 生成的 `SHA256SUMS` 放在同一目录；缺少或不匹配时
会在执行任何安装代码前失败。

Provider 配置、Model route、Keyring API Key、环境变量引用、项目数据和运行产物保持不变；
Core runtime、Native plugin、Workflow Skill、CLI、Configuration app 和程序依赖替换为目标版本。

## 按需运行与重启

Lifecycle MCP server 由 Codex 按需启动，Configuration app 只在运行
`scientific-figure gui` 时启动。未运行表示
正常 idle，不需要 `start-all`，也没有产品 daemon。

若更新时旧 Lifecycle MCP server 或 Configuration app 仍在运行，磁盘安装会完成，但结果返回：

```text
restart_required
```

保存当前任务和未保存的 Configuration draft，完全退出并重新打开 Codex。新的
Lifecycle MCP server 或 Configuration app
首次启动时会清理已经无人使用的旧 Core runtime 和 Native plugin cache；仍被进程引用的
目录不会删除。

状态退出码：

- `0`：本地版本已收敛；
- `2`：需要重载 Codex；
- `3`：组件版本不一致或远端有更新；
- `4`：安装损坏或状态无法读取。

使用 `status --verbose` 查看本地进程，`status --json` 获取机器可读结果，只有
`status --remote` 会访问 GitHub。

## 维护者发布

功能修改应先提交到 `main`。发布命令在隔离 Git worktree 中生成版本提交，不会暂存当前
工作区里的无关修改：

```bash
python3 scripts/release.py minor --publish
```

首次发布新的 Delivery 契约（`0.6.0`）前，还必须安装候选 Product bundle，完全重启
Codex，在新任务中实际启动 Lifecycle MCP server，并打开 Configuration app。确认本地
版本收敛后运行：

```bash
python3 scripts/record_release_acceptance.py --confirm-codex-restarted
```

该命令从 `scientific-figure status --json` 生成不含配置或凭据的验收证据。将对应 Release
notes 的 frontmatter 从 `status: draft` 改为 `status: approved` 后，`--publish` 才允许创建
tag。自动测试不能替代这次真实宿主重载证据。

也可以在发布后接着激活本机：

```bash
python3 scripts/release.py minor --publish --activate-local
```

Release Pipeline 会：

1. 从 `pyproject.toml` 计算并固定 Target version；
2. 生成 Workflow Skill、Citation、lockfile 和 Native plugin 版本镜像；
3. 推送 main 并等待该 commit 的 GitHub Actions；
4. CI 通过后创建不可变 tag；
5. tag workflow 构建 Product bundle、Core wheel、Release manifest 和 `SHA256SUMS`；
6. 使用已确认的 Release notes 创建 GitHub Release；
7. 中断后根据 Git、CI、tag 和 Release 的远端事实幂等继续。

已推送 tag 若指向不同 commit，发布会失败并要求使用新的 patch 版本，永不移动旧 tag。
Release 成功而本地需要重启时，Release 仍保持成功，组合命令返回退出码 `2`。

## 兼容入口

- `./install.sh --runtime-only --release VERSION`：只安装 Core；
- `./install.sh --codex`：不再表示 Core-only，会提示补充 `--release`；
- 无 Release 参数的旧源码安装仍可通过明确的 `--runtime-only` 路径使用。

安装事务日志经过脱敏，只保留最近 10 条。下载缓存、staging、临时备份以及不再运行的旧
产品文件会自动清理。
