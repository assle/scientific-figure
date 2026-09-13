<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="820">
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
  <strong>从澄清后的科研需求，到经过验证、可直接投稿的导出文件。</strong>
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="发表级复合科研图" width="820"><br>
  <sub>使用合成演示数据生成的示意性复合输出。</sub>
</p>

Scientific Figure Builder 帮助 Agent 将澄清后的需求转化为有来源的图表和素材、
完成组装的科研图、验证证据及可交付文件。测量数据由确定性的 Python/SVG 路径处理；
配置好的模型 Provider 只负责适合的图像生成与视觉分析任务。

## 环境要求

- Python 3.11 或更高版本。
- [`uv`](https://docs.astral.sh/uv/)。
- 使用原生 Agent 工作流时需要 Codex；也可以只安装核心运行时。

## 主要能力

- 可复现的折线、散点、柱状、热图、误差棒和多面板数据图。
- 以科学结构为先的机制图，支持可寻址节点和连接关系。
- 付费生图前先展示计划并取得确认。
- 确定性组装、分层验证、局部修复和中断恢复。
- 导出 PNG、SVG、PDF，以及可选的 PowerPoint 友好 SVG/PPTX。
- 原生 Codex 插件、本地运行时、CLI 和可选配置应用。

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="250"><br><sub>带误差范围的折线图</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="250"><br><sub>效率参数空间</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="330"><br><sub>多面板组合</sub></td>
    </tr>
  </table>
</p>

<p align="center">
  <sub>以上插图由合成演示数据生成，仅用于展示输出效果，不代表科研证据。</sub>
</p>

## 快速开始

下面每条命令都标明了应运行的位置。安装脚本和源码命令对当前目录有要求，安装后的
CLI 则可在任意目录运行。

### 1. 安装正式版本

克隆后，在仓库根目录运行：

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure          # 仓库根目录，包含 ./install.sh
./install.sh --codex --release latest --with-gui
```

`./install.sh` 是仓库内脚本，必须在包含它的目录运行。无桌面环境时省略
`--with-gui`。如果只需要核心运行时和 CLI：

```bash
./install.sh --runtime-only --release latest
```

### 2. 在任意目录使用已安装的 CLI

安装完成后，`scientific-figure` 启动器不依赖仓库位置，以下命令可在任意项目目录运行：

```bash
scientific-figure status
scientific-figure gui
scientific-figure update --latest
```

如果当前 Shell 找不到启动器，请使用 `~/.local/bin/scientific-figure`，或把
`~/.local/bin` 加入 `PATH`。运行这些已安装命令时不需要 `cd` 回仓库。

### 3. 从源码启动 GUI

开发时应进入 `scientific-figure-builder/`，即包含 `pyproject.toml` 的目录，再运行：

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui python -m figure_tools gui
```

源码目录不会自动安装 `scientific-figure` 启动器。要运行当前源码，请使用上面的命令；
要运行已安装版本，请先完成第 1 步，再在任意目录执行 `scientific-figure gui`。

## 配置应用

原生 Qt Quick 应用用于管理 Provider、模型路由和系统凭据。它不会打开浏览器、监听端口，
打开或保存配置时也不会访问 Provider。

<p align="center">
  <img src="assets/gui-model-routes.png" alt="模型角色路由界面" width="920">
</p>

<table>
  <tr>
    <td width="50%"><img src="assets/gui-providers.png" alt="Provider 端点和能力配置"></td>
    <td width="50%"><img src="assets/gui-credentials.png" alt="Keyring 凭据和连接测试"></td>
  </tr>
  <tr>
    <td align="center"><sub>端点、协议与显式声明的能力</sub></td>
    <td align="center"><sub>系统凭据与主动连接测试</sub></td>
  </tr>
</table>

建议按「Providers → 模型路由 → 凭据与连接 → 保存配置」完成首次配置。
应用编辑的是全局配置；界面里的修改先保留在窗口草稿中。

### 模型路由：每种任务交给哪个模型

- **Provider / 模型 ID**：先选已创建的端点，再填写该端点接受的模型 ID、Endpoint ID 或网关别名；不是模型的展示名称。
- **阶段推理**：为需求解析、规划、审核与修复分别运行结构化推理，不负责绘制数据曲线。
- **参考图分析**：读取参考图，提取布局、结构和语义信息。
- **图像生成**：生成非定量的图形素材或图形单元；测量数据图仍由 Python/SVG 生成。
- **图像编辑 / 继承生成**：使用参考图修订素材；「继承生成」表示复用图像生成角色的路由，不是增加一个新模型。
- **视觉验证**：检查生成素材和最终组合图的视觉内容。

### Providers：端点、协议与图像能力

- **新增 / 删除**：管理供模型角色引用的 Provider ID；它是本地配置标识，不是 API Key 或模型 ID。
- **类型**：按服务实际协议选择 `openai`、`anthropic` 或 `dashscope`，不按厂商品牌判断。DashScope Native 仅用于图像生成和编辑角色。
- **Base URL**：服务的 API 基址；应与所选协议匹配。
- **认证方式**：选择 API Key 通过 `x-api-key` 请求头还是 Bearer Token 发送；按接口文档设置。
- **Messages Path / Anthropic Version**：Anthropic Compatible 的请求路径和版本请求头；一般保留界面默认值，只有服务文档要求时才调整。
- **支持参考图编辑**：声明端点能够基于已有图像进行编辑。
- **支持生成参考图**：声明生成新图时可以附带参考图；不表示自动创建参考图。
- **支持多参考图**：允许同一请求使用多张参考图。
- **支持遮罩编辑**：允许用遮罩限定编辑区域。
- **支持结构控制**：允许请求携带结构控制信息。
- **支持原生透明通道**：声明模型可直接输出带透明通道的图像。
- **支持固定 Seed**：允许传入随机种子；不能保证服务在不同版本或环境下输出完全相同。
- **支持批量候选**：声明端点支持批量候选输出；勾选本身不会立即生成图片。

能力开关只声明服务已有的能力，不会让不支持的接口获得该功能。
界面按 Provider 类型显示可用选项；DashScope 不显示遮罩、结构控制和原生透明通道开关。

### 等待与重试设置：控制一次模型调用如何等待

Provider 设置作为角色的默认值，角色设置可单独覆盖；留空继承上级设置。
所有时长单位均为秒，尝试次数填写正整数。

- **连接等待**：建立网络连接的等待上限。
- **状态检查间隔**：检查请求状态的频率；检查状态不会重新发送模型请求。
- **连续无消息上限**：允许连续多久没有收到新消息；收到消息后重新计时。
- **单次调用总上限**：整次调用的总时间预算；收到消息不会重置它。
- **瞬态错误最多尝试次数**：包含首次请求在内的最大尝试次数，只用于可重试的瞬态错误。
- **退避基准 / 退避上限**：控制重试前等待时间的起点和上限，避免失败后立即连续重发。

### 阶段输出额度：控制结构化推理的输出预算

- **需求解析 / 规划 / 审核与修复初始额度**：分别设置三个阶段的初始 token 额度；留空继承配置，内置默认值为每阶段 8192。
- **单次输出上限**：限制一次输出可申请的最大额度；留空使用继承值或可识别的模型上限。
- 额度包含模型推理与最终输出，不等于实际消耗；同阶段恢复会沿用已发出的额度。它与等待秒数是两类独立限制。

### 凭据与连接：保存密钥并主动验证端点

- **选择 Provider**：凭据按端点独立管理。
- **API Key**：保存配置时写入操作系统 Keyring，不写入 YAML；输入框留空会保留已有凭据。
- **Credential ID**：配置文件引用系统凭据的标识，不是密钥内容。
- **环境变量回退**：填写变量名，例如 `PROVIDER_API_KEY`；适合通过 `key_env` 向无桌面环境提供凭据。
- **测试连接**：使用当前未保存的草稿主动访问服务，优先选择视觉角色；只有图像生成路径可用时，会先提示可能产生费用。
- **取消 / 移除凭据**：分别取消连接测试、移除所选 Provider 的系统凭据；不会把已有 Key 显示回输入框。

### 保存与配置范围

- **保存配置**：提交窗口草稿及密钥修改；普通保存不发起网络请求。
- **放弃修改**：丢弃当前未保存的编辑。
- **关于**：说明应用用途；侧栏显示当前全局配置文件路径。
- **项目级覆盖**：运行 `scientific-figure init /path/to/project`，在项目配置中设置，不在这个全局配置窗口切换项目。

配置优先级为：内置默认值 → 全局配置 → 项目配置 → 单次运行覆盖。Provider 类型、模型
角色、文件位置和最小 YAML 示例见[用户指南](docs/user-guide.zh-CN.md)。

## 工作流

让 Codex 使用已安装的 Skill，并说明源数据、目标图形、语言、尺寸或期刊要求以及导出格式：

```text
使用 scientific-figure-builder，根据 data.csv 创建可投稿的多面板科研图。
导出 PNG、SVG 和 PDF，并让 SVG 适合在 PowerPoint 中继续编辑。
```

<p align="center">
  <img src="assets/workflow.svg" alt="需求澄清、规划、审批、执行、审核与修复、导出" width="900">
</p>

测量数据和定量图表始终走确定性的 Python/SVG 路径；非定量的图形单元可以使用已配置的
Provider 路由。最终组装、验证、修复和导出在本地确定性完成。只有需要补充信息、确认计划、
选择修复或确认生成摘要时，工作流才会暂停。

## 更新、状态与卸载

安装后可在任意目录运行：

```bash
scientific-figure update --latest
scientific-figure status
```

更新会保留 Provider 配置、凭据引用、项目数据和运行产物。如果 `status` 返回
`restart_required`，请先保存当前工作，再完全退出并重新打开 Codex，让新的 MCP/GUI
进程加载已激活的运行时。只有需要主动查询 GitHub 最新版本时才使用
`scientific-figure status --remote`。

先回到仓库根目录预览卸载内容，再选择所需范围：

```bash
./uninstall.sh --dry-run
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh              # 删除核心运行时和 CLI，保留配置
./uninstall.sh --all        # 同时删除全局配置及其引用的凭据
```

原生插件和核心运行时拥有独立生命周期，完整卸载需要同时移除两者。除非明确使用 `--all`
或 `--config`，卸载器会保留全局配置和凭据。

## 文档

- [用户指南](docs/user-guide.zh-CN.md)：安装、配置、工作流、更新与卸载。
- [贡献指南](CONTRIBUTING.md)与[安全策略](SECURITY.md)。

## 开发

开发命令应在 `scientific-figure-builder/` 中运行：

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uvx pyright --pythonpath .venv/bin/python figure_tools install
```

权威 Skill 位于 `scientific-figure-builder/SKILL.md`。修改后回到仓库根目录运行：

```bash
python3 scripts/sync_plugin_bundle.py
```

配置应用界面发生变化后，在仓库根目录重新生成 README 截图：

```bash
uv run --frozen --directory scientific-figure-builder --extra gui \
  python ../scripts/capture_readme_screenshots.py
```

示例配图使用同一套合成演示数据，可独立重新生成：

```bash
uv run --frozen --directory scientific-figure-builder \
  python ../scripts/generate_readme_examples.py
```

## 许可

[MIT](./LICENSE)
