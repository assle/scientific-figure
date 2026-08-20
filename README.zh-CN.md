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
  <a href="https://www.volcengine.com/product/ark"><img src="https://img.shields.io/badge/Ark-Volcengine-red" alt="Ark"></a>
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

需要：Python 3.11+、[uv](https://docs.astral.sh/uv/)，以及你实际使用的
[OpenCode](https://opencode.ai/) 或 Codex。只需在仓库检出目录执行一次安装命令，
仓库本身不会变成你项目的一部分。

### 配置模型接口（可选）

模型角色可全局配置在 `~/.config/scientific-figure-builder/config.yaml`，
项目级覆盖在 `.scientific-figure/project.yaml`；环境变量优先级最高。
Provider 实例只使用 `openai` 或 `anthropic` 两种适配器类型。OpenAI 兼容
适配器会在内部选择 Images 或 Responses；`base_url` 应填写 API 根地址，
不要填写完整操作地址。

```bash
export ARK_API_KEY="<Agent Plan 专属密钥>"
```

```yaml
# ~/.config/scientific-figure-builder/config.yaml（不要写入 API Key）
providers:
  openai:
    type: openai
    base_url: https://ark.cn-beijing.volces.com/api/plan/v3
    key_env: ARK_API_KEY
    supports_image_edit: true
  anthropic:
    type: anthropic
    base_url: https://ark.cn-beijing.volces.com/api/plan
    key_env: ARK_API_KEY
    auth_scheme: bearer
    messages_path: /v1/messages
models:
  image_generate: {model: "<Seedream 模型>", provider: openai}
  vision_analyze: {model: "<视觉分析模型>", provider: anthropic}
  vision_validate: {model: "<校验模型>", provider: anthropic}
```

`image_edit` 是可选角色。没有显式覆盖时，生成式位图的参考图修改会复用
`image_generate`。脚本图、标签、公式和 SVG 元素必须修改源参数后重新渲染，
不能交给图片编辑模型。Anthropic 兼容接口只承担视觉分析和校验。

迁移期间仍兼容旧的 `protocol: responses` 配置，以及 `ARK_IMAGE_*`、
`ARK_*_BASE_URL` 环境变量。
如果使用自定义 `key_env`，还需要在 OpenCode/Codex 的 MCP 配置中转发这个
环境变量。

> 纯本地绘图？跳过此步，运行 `./install.sh --without-ark`

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
│   ├── ark/             # Ark 客户端 + 传输层（mock/real）
│   ├── plotting/        # 图表规范、数据、配方、渲染器
│   ├── validation/      # 几何规则 + VLM 审核 + 证据图
│   ├── assembly/        # 图形合成
│   └── export/          # PNG/SVG/PDF/PPTX 导出
├── schemas/             # 6 个版本化 JSON Schema
├── templates/           # 默认配置 + 绘图配方
├── references/          # 路由/工作流/Ark 文档
└── tests/               # 单元/集成/端到端测试
```

## 开源许可

[MIT](./LICENSE)
