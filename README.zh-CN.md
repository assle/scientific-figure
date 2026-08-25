<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?logo=opensourceinitiative&logoColor=white" alt="License"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-Required-purple?logo=astralshuv&logoColor=white" alt="uv"></a>
  <a href="https://opencode.ai/"><img src="https://img.shields.io/badge/OpenCode-Ready-orange" alt="OpenCode"></a>
  <img src="https://img.shields.io/badge/Providers-Configurable-blue" alt="Configurable providers">
  <img src="https://img.shields.io/badge/Plots-Reproducible-success" alt="Reproducible">
</p>

---

## 项目简介

从自然语言需求到**可复现的发表级**科研配图。数据图由 Python/SVG 确定性渲染；AI 图像模型只生成隔离的非量化素材。每次输出跨运行字节级一致。

<p align="center">
  <img src="assets/example_compound.png" alt="复合图示例" width="640">
</p>

## 功能特性

| | 功能 | 说明 |
|---|---|---|
| 📊 | **确定性数据图** | 折线/散点/柱状/热图/误差棒/多面板 - CSV 转图，字节级可复现 |
| 🎨 | **AI 素材生成** | 可配置图像模型生成隔离视觉元素（设备示意图等），自动去背景 |
| 🏷️ | **SVG 标签** | 箭头、公式、标注，全部确定性生成 |
| 🧩 | **自动拼装** | 多元素按 z-order 合成，导出 PNG/SVG/PDF |
| 🎯 | **导出场景** | `general` 输出跨工具通用的路径文字，`ppt` 输出适合 PowerPoint 的可编辑 SVG |
| ✅ | **两层校验** | 确定性几何规则 + 多模态 VLM 审核，错误阻断导出 |
| 🔄 | **可复现运行** | 版本化 run 目录、缓存、断点恢复 |

## 快速开始

### 选择导出场景

SVG 输出支持两种场景：

- `general`（默认）：文字转成路径，跨工具兼容性最好。
- `ppt`：文字保留为可编辑 `<text>`，并做 PowerPoint 取消组合/转换为形状的兼容归一化。

可在项目配置中设置：

```yaml
export:
  export_target: ppt
```

也可以在单次工具调用或运行时通过 `export_target: "ppt"` 覆盖。

### 选择图宽

未指定图宽时，skill 会询问使用哪个常见出版图宽：

- 半栏图：6.5 cm
- 通栏图：14 cm

也可以在结构化请求中设置：

```yaml
figure_width_cm: 6.5
```

高度会沿用默认画布比例自动计算，除非你另外指定自定义高度。

### 选择语言和风格

未指定时，skill 会在规划前先询问：

- 图内文字语言：中文（`zh`）或英文（`en`）
- 图风格：`default` 出版风，或自定义参考风格

已确定时可直接写在结构化请求里：

```yaml
language: zh
style: default
```

### 安装

一次安装，**OpenCode 和 Codex 全局可用**：

```bash
./install.sh
```

也可以直接从 GitHub 全局安装，无需手动克隆：

```bash
curl -fsSL https://raw.githubusercontent.com/assle/scientific-figure/main/install.sh | sh
```

这会把你电脑用户级目录中的 skill、命令和私有运行时安装好。你**不需要**把
仓库复制到每个项目里。安装器默认同时写入 OpenCode 和 Codex 的配置。

如果只想安装到某一个项目：

```bash
./install.sh --project /path/to/your-project
```

只想安装其中一种 agent：

```bash
./install.sh --opencode-only
./install.sh --codex-only
```

全局安装位置：

- Skill：`~/.config/opencode/skills/scientific-figure-builder`
- Command：`~/.config/opencode/commands/scientific-figure.md`
- Codex Skill：`~/.codex/skills/scientific-figure-builder`
- Codex 配置：`~/.codex/config.toml`
- Runtime：`~/.local/share/scientific-figure-builder`
- 启动器：`~/.local/bin/scientific-figure`（若不在 `PATH`，安装器会提示）

需要：Python 3.11+、[uv](https://docs.astral.sh/uv/)，以及你实际使用的
[OpenCode](https://opencode.ai/) 或 Codex。只需在仓库检出目录执行一次安装命令，
仓库本身不会变成你项目的一部分。

## 安装

在仓库检出目录执行一次即可：

```bash
./install.sh
```

只装某个 agent，或安装到指定项目：

```bash
./install.sh --target codex         # 或：--target opencode
./install.sh --project /path/to/project
```

**安装会做什么。**

- 在 `~/.local/share/scientific-figure-builder/` 创建私有运行环境（包含包、Schema、模板、参考资料的虚拟环境）。
- 把 **skill** 安装到你的 agent，使其能调用本工具：
  - Codex：`~/.codex/skills/scientific-figure-builder/`
  - OpenCode：`~/.config/opencode/skills/scientific-figure-builder/`
- 添加 OpenCode **斜杠命令**：`~/.config/opencode/commands/scientific-figure.md`
- 注册 MCP **服务条目**（用于启动 `figure_tools.server`）：
  - Codex：`~/.codex/config.toml` 中的 `[mcp_servers.scientific-figure]`
  - OpenCode：`~/.config/opencode/opencode.json` 中的 `mcp.scientific-figure`
- 默认安装包含 GUI extra、Keyring 支持和 GUI 资源；全局安装会创建
  `scientific-figure` 启动器，项目级安装不会创建全局启动器。
- 把配置好的供应商环境变量（各 provider 的 `key_env` 及 `SCI_FIG_*` 模型覆盖项）转发给 MCP 宿主。
- 编辑已有配置前会先备份。

不会把 API Key 写入磁盘。GUI 中的 API Key 使用密码模式并保存到系统
Keyring；服务器、CI 和无桌面环境仍可只使用 `key_env` 环境变量。

## 卸载

移除已安装的软件及其 MCP 条目，不影响本仓库和无关配置：

```bash
./uninstall.sh                        # 全局安装
./uninstall.sh --config               # 同时删除 ~/.config/scientific-figure-builder/
./uninstall.sh --all                  # 全局 + 用户配置
./uninstall.sh --project /path/to/project   # 删除某项目内的安装
./uninstall.sh --dry-run              # 先预览，不改动任何东西
```

**卸载会删除什么。**

- 私有运行环境：`~/.local/share/scientific-figure-builder/`
- 已安装的 skill：
  - `~/.codex/skills/scientific-figure-builder/`
  - `~/.config/opencode/skills/scientific-figure-builder/`
- OpenCode 斜杠命令：`~/.config/opencode/commands/scientific-figure.md`
- MCP 服务条目（只删 `scientific-figure`，其它服务器保留）：
  - Codex：`~/.codex/config.toml` 中的 `[mcp_servers.scientific-figure]`
  - OpenCode：`~/.config/opencode/opencode.json` 中的 `mcp.scientific-figure`
- 启动器：只删除本工具标记的 `scientific-figure`，无关同名文件会保留并警告。
- 加 `--config`：删除用户配置目录 `~/.config/scientific-figure-builder/`
  并先清理该配置引用的 Keyring 凭据；Keyring 清理失败时保留配置。
- 加 `--project DIR`：删除该项目 `.opencode/` 与 `.codex/` 下的 skill、命令及 MCP 条目

其它 agent 配置、项目和本仓库均不受影响。被删除的目录可通过重新执行 `./install.sh` 恢复。

### 配置模型接口（可选）

也可以直接运行原生 Qt Quick/QML 中文配置窗口：

```bash
scientific-figure gui
# 或：python -m figure_tools gui
```

窗口支持新增、重命名和删除 Provider、编辑 OpenAI/Anthropic 高级字段、
安全保存 API Key，以及为当前未保存草稿主动测试连接。连接测试只在用户
点击后执行，视觉路径使用最小确定性图片；生成路径可能产生 Provider 费用，
会在执行前确认。`image_edit` 省略时继承 `image_generate`，不要求重复配置。
界面采用紧凑侧栏、路由卡片、状态徽标和固定保存栏；QML 只负责展示，配置、
Keyring、校验和连接测试仍复用现有 Python 服务。

每个模型角色都会绑定到一个 provider，因此不同流程可以使用不同厂商。
在 `~/.config/scientific-figure-builder/config.yaml` 全局配置，在
`.scientific-figure/project.yaml` 做项目级覆盖；`SCI_FIG_*` 环境变量覆盖
模型 id，各 provider 的 `key_env` 指定环境变量回退名；若存在 `credential_id`，
系统 Keyring 凭据优先。

Provider 只使用两种接口方言：`openai` — 生图走 `/images/generations`、视觉走
`/responses`；`anthropic` — 仅视觉走 `/messages`。`base_url` 应填 API 根地址，
不要填完整操作地址。

```yaml
# ~/.config/scientific-figure-builder/config.yaml（不要写入 API Key）
providers:
  deepseek:
    type: openai
    base_url: https://api.deepseek.com/           # DeepSeek 多模态，走 /responses
    key_env: DEEPSEEK_API_KEY
  ark_seedream:
    type: openai
    base_url: https://ark.cn-beijing.volces.com/api/plan/v3  # Seedream，走 /images/generations
    key_env: ARK_API_KEY
    supports_image_edit: true
models:
  image_generate: {model: "<Seedream 模型 id>", provider: ark_seedream}
  vision_analyze: {model: "deepseek-v4-flash-vision-exp", provider: deepseek}
  vision_validate: {model: "deepseek-v4-flash-vision-exp", provider: deepseek}
```

`image_generate` 必须是真正的图片生成模型；`vision_analyze` /
`vision_validate` 是多模态（读图）模型，可以是与分析步骤同一厂商。
`image_edit` 为可选角色，省略时回退到 `image_generate`。图表、标签、公式和
SVG 元素由确定性引擎渲染，绝不发送给模型。凭证永不写入配置、日志、产出物
或清单；安装脚本会自动转发用户配置里的所有 `key_env` 到 MCP 宿主。若只做
本地开发，可用 `SCIENTIFIC_FIGURE_CONFIG` 指向自己的配置文件，而不必改
`~/.config/...`。

### 在 OpenCode 中使用

```text
使用 scientific-figure-builder，根据 data.csv 画一张论文用折线图
```

或用命令：

```bash
/scientific-figure init
/scientific-figure plan 根据 data.csv 生成多面板科研图
/scientific-figure run
/scientific-figure validate
/scientific-figure export
```

## 效果展示

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="280"><br><sub>折线图</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="280"><br><sub>热图</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="280"><br><sub>多面板</sub></td>
    </tr>
  </table>
</p>

## 开发

```bash
cd scientific-figure-builder
uv sync
uv run pytest
```

可选的 PowerPoint 端到端测试会打开本机 Microsoft PowerPoint，验证
`export_target=ppt` 的 SVG 能插入、转换并取消组合：

```bash
RUN_POWERPOINT_E2E=1 uv run pytest tests/e2e/test_powerpoint_import.py -q
```

首次运行可能需要在 macOS 提示中授予 PowerPoint 访问测试临时目录的权限。

## 项目结构

```
scientific-figure-builder/
├── figure_tools/        # Python 核心包
│   ├── providers/       # Provider 传输层 + 客户端（OpenAI/Anthropic）
│   ├── plotting/        # 图表规范、数据、配方、渲染器
│   ├── validation/      # 几何规则 + VLM 审核 + 证据图
│   ├── assembly/        # 图形合成
│   └── export/          # PNG/SVG/PDF/PPTX 导出
├── schemas/             # 6 个版本化 JSON Schema
├── templates/           # 默认配置 + 绘图配方
├── references/          # 路由/工作流/provider 文档
└── tests/               # 单元/集成/端到端测试
```

## 开源许可

[MIT](./LICENSE)
