# 用户指南

本文只说明公开的安装、配置、科研图工作流和卸载方式。内部架构见
[`CONTEXT.md`](../CONTEXT.md) 与 ADR；维护者发布流程见
[`operations/release-and-local-activation.md`](operations/release-and-local-activation.md)。

## 安装方式

运行环境需要 Python 3.11+ 和 [`uv`](https://docs.astral.sh/uv/)。

安装完整 Codex 集成和可选配置应用：

```bash
./install.sh --codex --release latest --with-gui
```

无桌面环境时省略 `--with-gui`。如果只安装核心运行时和 CLI，不安装 Agent 集成：

```bash
./install.sh --runtime-only --release latest
```

使用 `--release vX.Y.Z` 可固定正式版本；使用 `--bundle FILE` 可激活本地 Product
bundle。本地 bundle 旁必须有 Release 生成的 `SHA256SUMS`。

Unix 默认启动器位于 `~/.local/bin/scientific-figure`。安装器不会修改 Shell 启动文件，
因此必要时需要自行把 `~/.local/bin` 加入 `PATH`。

## 配置

### 配置层级

有效配置按以下顺序合并，后者优先：

1. 内置默认值；
2. 全局配置；
3. 项目配置；
4. 单次运行覆盖。

全局文件为 `$XDG_CONFIG_HOME/scientific-figure-builder/config.yaml`；Unix 默认路径是
`~/.config/scientific-figure-builder/config.yaml`。可用 `SCIENTIFIC_FIGURE_CONFIG`
指定另一个绝对路径。

`scientific-figure init PROJECT_DIR` 会在 `PROJECT_DIR/.scientific-figure/` 下创建项目
配置。这些文件不含凭据，可用于覆盖该项目的画布、导出、模型、Provider 和验证默认值。

### 配置应用

首次安装未包含 GUI 时可以稍后补装：

```bash
scientific-figure install-gui
scientific-figure gui
```

在应用中依次完成：

1. 创建 Provider 并选择接口类型。
2. 填写端点，只声明它实际支持的能力。
3. 把 API Key 保存到系统凭据存储，或通过 `key_env` 指定环境变量。
4. 将模型角色绑定到该 Provider 和固定的模型或端点 ID。
5. 需要时主动运行连接测试。

打开或保存配置不会访问 Provider；只有明确点击连接测试时才会使用当前草稿发起请求。

### Provider 类型与模型角色

支持的 Provider 类型为：

| 类型 | 可承担的任务 |
| --- | --- |
| `openai` | 推理、视觉、图像生成，以及显式声明的图像编辑能力 |
| `anthropic` | 通过 Messages API 完成推理和视觉任务 |
| `dashscope` | 仅用于原生图像生成和编辑 |

模型角色包括可选的 `phase_reasoning`、`image_generate`、可选且继承
`image_generate` 的 `image_edit`、`vision_analyze` 和 `vision_validate`。只有 Provider
类型和显式能力与角色匹配时，路由才可用。

### 最小无界面配置

```yaml
providers:
  openai_main:
    type: openai
    base_url: https://api.example.com/v1
    key_env: OPENAI_API_KEY
    supports_image_edit: true

models:
  phase_reasoning: {provider: openai_main, model: reasoning-model}
  image_generate:  {provider: openai_main, model: image-model}
  vision_analyze:  {provider: openai_main, model: vision-model}
  vision_validate: {provider: openai_main, model: vision-model}
```

不要把 API Key 写入 YAML；应在启动 Codex 或运行时的环境中提供相应变量。当没有任何可用
的真实 Provider 凭据时，运行时会使用确定性的无网络 Mock Transport。该模式适合测试和
离线检查工作流，但它生成的素材不能作为真实模型调用的证据。

## 科研图工作流

### 开始任务

向 Agent 说明科学目标和允许使用的文件，并提供重要约束：图宽、语言、投稿目标、风格、
必须包含的内容和导出格式。

```text
使用 scientific-figure-builder，根据 results.csv 和 diagram-notes.md 创建双面板科研图。
使用英文标签、14 cm 通栏宽度，并导出 PNG、SVG 和 PDF。
```

Codex 集成只公开两个生命周期工具：一个初始化项目配置，另一个推进科研图工作流。正常任务
始终沿同一生命周期推进，不由调用方临时拼接底层绘图工具。

### 决策点

生命周期依次经过需求澄清、规划、执行、审核与修复、导出。Agent 根据返回的状态和下一动作：

- 在生产开始前回答必要问题；
- 在付费生图前审核计划或生成摘要；
- 批准计划、修改生成选择或请求局部修复；
- Provider 长任务仍在运行时恢复同一个 operation；
- 只把通过验证的导出文件视为完成结果。

测量值、标签、公式、几何、组装和导出保持确定性。图像 Provider 只拥有计划中明确指定的
非量化生成单元。视觉复核可以补充确定性检查，但不能覆盖确定性失败。

### 输出与恢复

每个任务使用独立的 run 目录，保存带版本的状态、计划、素材、验证证据和导出文件。工作流
返回 `in_progress` 时应恢复同一个 operation ID；另起任务可能重复付费调用。上游变化只会
使受影响的下游产物失效，因此无关且仍有效的素材可以复用。

默认正式输出为 PNG、SVG 和 PDF。需要在 PowerPoint 中编辑 SVG 文字时选择 `ppt` 导出
目标；`general` 更强调 SVG 的通用兼容性。

## 更新与诊断

```bash
scientific-figure update --latest
scientific-figure status
scientific-figure status --verbose
scientific-figure status --remote
```

`update` 默认保持当前 Codex/运行时安装形态和 GUI 选择。只有需要改变这些选择时才显式使用
`--release vX.Y.Z`、`--with-gui`、`--without-gui`、`--codex` 或 `--runtime-only`。

状态退出码：

| 退出码 | 含义 |
| ---: | --- |
| `0` | 本地组件版本已收敛。 |
| `2` | 新版本已写入磁盘，需要重启 Codex 以重新加载运行组件。 |
| `3` | 组件不一致，或 `--remote` 发现可用更新。 |
| `4` | 活动运行时缺失或不可读。 |

MCP 服务和配置应用都按需启动，不需要常驻 daemon，也没有手动 `start-all` 步骤。

## 卸载

原生插件和核心运行时分别管理。先预览：

```bash
./uninstall.sh --dry-run
```

常见范围：

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh                         # 核心运行时和 CLI
./uninstall.sh --config                # 核心、CLI、全局配置和凭据
./uninstall.sh --all                   # 再包括旧集成、全局配置和凭据
./uninstall.sh --runtime-only --project DIR
```

默认卸载核心运行时会保留全局 Provider 配置和凭据。凭据清理只处理本产品全局配置引用的
条目；如果系统凭据存储清理失败，配置文件会被保留。
