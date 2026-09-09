<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/GUI-可选-3B6FF5" alt="可选 GUI">
  <a href="https://github.com/assle/scientific-figure/releases/latest"><img src="https://img.shields.io/github/v/release/assle/scientific-figure?label=版本" alt="最新版本"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License"></a>
</p>

<p align="center">
  通过一条受控工作流构建可复现、可投稿的科研配图。
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="发表级复合科研图" width="820">
</p>

Scientific Figure Builder 帮助 Agent 将澄清后的需求转化为有来源的图表和素材、
完成组装的科研图、验证证据及可交付文件。测量数据由确定性的 Python/SVG 路径处理；
配置好的模型 Provider 只负责适合的图像生成与视觉分析任务。

## 主要能力

- 可复现的折线、散点、柱状、热图、误差棒和多面板数据图。
- 以科学结构为先的机制图，支持可寻址节点和连接关系。
- 付费生图前先展示计划并取得确认。
- 确定性组装、分层验证、局部修复和中断恢复。
- 导出 PNG、SVG、PDF，以及可选的 PowerPoint 友好 SVG/PPTX。
- 原生 Codex 插件、本地运行时、CLI 和可选配置应用。

## 环境要求

- Python 3.11 或更高版本。
- [`uv`](https://docs.astral.sh/uv/)。
- 使用原生 Agent 工作流时需要 Codex；也可以只安装核心运行时。

## 安装

克隆仓库并激活最新正式 Codex 版本：

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure
./install.sh --codex --release latest --with-gui
```

无桌面环境时省略 `--with-gui`。如果只需要核心运行时和 CLI：

```bash
./install.sh --runtime-only --release latest
```

如果当前 Shell 找不到启动器，请使用 `~/.local/bin/scientific-figure`，或把
`~/.local/bin` 加入 `PATH`。

## 配置

打开可选配置应用：

```bash
scientific-figure gui
```

先创建 Provider，再绑定需要的模型角色。应用保存的 API Key 会进入操作系统凭据存储，
不会写入 YAML。无桌面环境可在 Provider 中设置 `key_env`，再通过环境变量提供凭据。

需要覆盖全局默认值时，在项目中初始化本地配置：

```bash
scientific-figure init /path/to/project
```

配置优先级为：内置默认值 → 全局配置 → 项目配置 → 单次运行覆盖。Provider 类型、模型
角色、文件位置和最小 YAML 示例见[用户指南](docs/user-guide.zh-CN.md)。

## 工作流

让 Codex 使用已安装的 Skill，并说明源数据、目标图形、语言、尺寸或期刊要求以及导出格式：

```text
使用 scientific-figure-builder，根据 data.csv 创建可投稿的多面板科研图。
导出 PNG、SVG 和 PDF，并让 SVG 适合在 PowerPoint 中继续编辑。
```

工作流依次经过：

```text
需求澄清 → 规划 → 审批 → 执行 → 审核与修复 → 导出
```

只有需要补充信息、确认计划、选择修复或确认生成摘要时才会暂停。摘要和预览不代表成品；
最终文件必须经过验证和导出后才会报告。

## 更新与状态

```bash
scientific-figure update --latest
scientific-figure status
```

更新会保留 Provider 配置、凭据引用、项目数据和运行产物。如果 `status` 返回
`restart_required`，请先保存当前工作，再完全退出并重新打开 Codex，让新的 MCP/GUI
进程加载已激活的运行时。

只有需要主动查询 GitHub 最新版本时才使用 `scientific-figure status --remote`；普通状态
检查完全在本地完成。

## 卸载

先预览源码卸载器将删除的内容：

```bash
./uninstall.sh --dry-run
```

再选择所需范围：

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh              # 删除核心运行时和 CLI，保留配置
./uninstall.sh --all        # 同时删除全局配置及其引用的凭据
```

原生插件和核心运行时拥有独立生命周期，完整卸载需要同时移除两者。除非明确使用 `--all`
或 `--config`，卸载器会保留全局配置和凭据。

## 文档

- [用户指南](docs/user-guide.zh-CN.md)：配置、工作流、更新与卸载。
- [发布与本地激活](docs/operations/release-and-local-activation.md)：维护者发布门禁与运行时激活语义。
- [产品术语](CONTEXT.md)：领域和生命周期的权威定义。
- [贡献指南](CONTRIBUTING.md)与[安全策略](SECURITY.md)。
- [架构决策](docs/adr/)。

## 开发

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uvx pyright --pythonpath .venv/bin/python figure_tools install
```

权威 Skill 位于 `scientific-figure-builder/SKILL.md`。修改后运行
`python3 scripts/sync_plugin_bundle.py`；不要直接编辑自动生成的插件副本。

## 许可

[MIT](./LICENSE)
