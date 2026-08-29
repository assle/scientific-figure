<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/GUI-Qt_Quick-3B6FF5" alt="Qt Quick GUI">
  <img src="https://img.shields.io/badge/Providers-可配置-blue" alt="Provider 可配置">
  <img src="https://img.shields.io/badge/图表-可复现-success" alt="图表可复现">
  <img src="https://img.shields.io/badge/版本-0.1.0-orange" alt="开发版本 0.1.0">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License"></a>
</p>

<p align="center">
  把澄清后的科研配图需求转化为可复现素材、组合图、验证证据和出版级输出。
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="发表级复合科研图" width="820">
</p>

## 产品与交付形态

Scientific Figure Builder 是完整的开源产品，不等同于其中任一组件。它由工作流
Skill、本地生命周期 MCP 服务、确定性核心运行时、CLI 和原生配置应用共同组成。

当前 `0.1.0` 开发版本以面向 Codex 和 OpenCode 的 **Agent 集成包** 交付，尚不是
原生 Codex 插件：标准插件清单以及由宿主管理的安装、升级和卸载生命周期仍在建设中。
这个区分既准确描述当前安装契约，也明确了项目正在走向干净、规范化插件交付的方向。

| 组件 | 职责 |
|---|---|
| 工作流 Skill | 告诉 Calling Agent 何时以及如何执行工作流 |
| 生命周期 MCP 服务 | 提供项目初始化和生命周期推进能力 |
| 核心运行时 | 在本地执行绘图、组装、验证和导出 |
| 配置应用 | 管理 Provider、Model route 和系统凭据 |
| Agent 集成 | 让 Codex 或 OpenCode 发现 Skill 与 MCP 服务 |

## 能得到什么

| | 能力 | 结果 |
|---|---|---|
| 📊 | 确定性数据图 | 从 CSV 生成折线、散点、柱状、热图、误差棒和多面板图 |
| 🎨 | Provider-neutral AI 素材 | 带来源记录和自动去背景的隔离非量化视觉素材 |
| 🧩 | 精确拼装 | 使用 Python/SVG 组合面板、标签、箭头和公式 |
| ✅ | 两层验证 | 权威几何规则 + 多模态模型语义补充 |
| 📦 | 出版导出 | PNG、SVG、PDF，以及可选的 PowerPoint 友好 SVG/PPTX |

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="280"><br><sub>可复现折线图</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="280"><br><sub>确定性数据映射热图</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="330"><br><sub>多面板组合</sub></td>
    </tr>
  </table>
</p>

## 可视化模型路由

原生 Qt Quick 应用用于管理全局 Model role、Provider 和系统凭据。打开或保存
配置不会启动浏览器、本地 Web 服务，也不会自动访问 Provider。

<p align="center">
  <img src="assets/gui-model-routes.png" alt="模型角色路由界面" width="920">
</p>

<table>
  <tr>
    <td width="50%"><img src="assets/gui-providers.png" alt="Provider 端点和能力配置"></td>
    <td width="50%"><img src="assets/gui-credentials.png" alt="Keyring 凭据和连接测试"></td>
  </tr>
  <tr>
    <td align="center"><sub>端点、协议与模型能力</sub></td>
    <td align="center"><sub>Keyring 凭据与主动连接测试</sub></td>
  </tr>
</table>

- **Providers**：负责端点增删改、接口方言和可选能力。
- **凭据与连接**：把 API Key 保存到操作系统 Keyring；只有用户点击时才测试当前未保存草稿。
- **模型路由**：把 `vision_analyze`、`image_generate`、可选 `image_edit` 和
  `vision_validate` 绑定到 Provider 与固定模型 ID。
- 没有 Provider 时，路由选择器会禁用并直接引导到新增流程。

## 快速开始

### 1. 安装

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure
./install.sh
```

当前 Agent 集成包会为 Codex 和 OpenCode 注册工作流 Skill 与双入口生命周期 MCP
服务、安装核心运行时，并创建 `~/.local/bin/scientific-figure` 启动器。

### 2. 配置 Provider

```bash
scientific-figure gui
```

先创建 Provider，再分配 Model role。API Key 不会进入 YAML：全局配置只保存稳定
的 `credential_id`；服务器、CI 和无桌面环境仍可使用 `key_env` 环境变量。

### 3. 让 Agent 开始工作

```text
使用 scientific-figure-builder，根据 data.csv 创建发表级多面板科研图。
导出 PNG、SVG 和 PDF，并让 SVG 适合在 PowerPoint 中继续编辑。
```

生命周期 Orchestrator 会先把导出目标、图宽、语言和风格记录到 Figure brief，
再在付费生成前展示 Figure plan 与线框图。Calling Agent 根据 Orchestrator 返回的
下一动作继续，不再手动串联底层工具。

## 核心规则

```text
精确数据、坐标轴、公式、文字和几何结构  →  Python / SVG
隔离的非量化视觉素材                    →  配置的图像 Provider
最终组合与导出                          →  本地确定性流水线
```

AI 图像模型不会绘制数据图或最终复合图。确定性检查保持权威；视觉模型可以补充
语义说明，但不能把几何检查的失败改成通过。

## 最小 Provider 配置

GUI 会替你写入这些元数据；配置中刻意不包含 API Key：

```yaml
providers:
  vision_provider:
    type: openai
    base_url: https://api.example.com/v1
    key_env: VISION_API_KEY
  image_provider:
    type: openai
    base_url: https://images.example.com/v1
    key_env: IMAGE_API_KEY
    supports_image_edit: true

models:
  vision_analyze:  {provider: vision_provider, model: vision-model}
  image_generate:  {provider: image_provider,  model: image-model}
  vision_validate: {provider: vision_provider, model: vision-model}
```

省略 `image_edit` 即表示继承 `image_generate`。Keyring 凭据优先于环境变量回退。

## 导出目标

| 目标 | 适用场景 | SVG 文字 |
|---|---|---|
| `general` | 投稿、浏览器和通用矢量工具 | 转换为兼容性更好的路径 |
| `ppt` | PowerPoint 编辑和取消组合 | 保留为可编辑文字 |

## 安装选项

```bash
./install.sh --codex-only
./install.sh --opencode-only
./install.sh --project /path/to/project
./install.sh --verify
```

<details>
<summary><strong>安全卸载</strong></summary>

```bash
./uninstall.sh                  # 保留用户配置和 Keyring 凭据
./uninstall.sh --config         # 同时清理配置引用的 Keyring 条目
./uninstall.sh --project DIR    # 删除指定项目集成
./uninstall.sh --dry-run
```

卸载器只删除本工具标记的启动器和 MCP 条目；Keyring 清理失败时会保留用户配置。
</details>

## 版本管理

Scientific Figure Builder 遵循[语义化版本](https://semver.org/lang/zh-CN/)。
`scientific-figure-builder/pyproject.toml` 是 Product version 的唯一权威来源；CLI
和生命周期 MCP 服务读取已安装 Python 包的版本。可通过下面的命令检查：

```bash
scientific-figure --version
```

项目当前处于 1.0 之前，`0.y.z` 版本仍可能调整公开接口。只有仓库同时存在不可变的
`vX.Y.Z` Git tag 和对应 GitHub Release 时，才构成一次正式发布。Schema、Phase
prompt 和绘图 recipe 各自拥有独立兼容性版本，不随 Product version 自动变化。

## 开发

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uv run --extra gui python -m figure_tools gui
```

延伸阅读：

- [领域术语](./CONTEXT.md)
- [Provider 接口](./scientific-figure-builder/references/provider-interfaces.md)
- [工作流细节](./scientific-figure-builder/references/workflow-details.md)
- [安全策略](./SECURITY.md)
- [GUI 跨平台验证](./docs/verification/gui-platforms.md)

## 开源许可

[MIT](./LICENSE)
