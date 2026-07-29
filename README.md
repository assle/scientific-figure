# Scientific Figure Builder

OpenCode 优先的科研论文配图编排技能：理解配图需求 -> 分解为渲染任务 -> 路由到正确引擎（Python 数据图 / SVG / 火山方舟 Ark 图像与视觉模型）-> 校验 -> 拼装最终 PNG/SVG/PDF。

**不是一次性文生图**。图像模型只产出隔离的非量化素材；数据图、坐标轴、刻度、数字、公式、最终拼装全部由确定性 Python/SVG 完成，可复现。

完整设计与阶段计划见 [`scientific-figure-builder-v1-plan.md`](./scientific-figure-builder-v1-plan.md)。

## 特性

- 6 个版本化 JSON Schema（figure-plan / plot-spec / asset-manifest / style-bible / run-state / validation-report）
- 6 种固定配方：line / scatter / bar / heatmap / error_bar / multipanel，CSV->图可复现（PNG/SVG/PDF 跨运行字节一致）
- SVG 原语 + LaTeX(mathtext)->SVG + 无成本布局线框
- 图像合成器 + PNG/SVG/PDF 导出 + 可选 PPTX
- 运行状态：预算/重试/缓存/审批检查点、版本化 run 目录、断点恢复与增量失效
- 火山方舟 Ark 集成：参考图分析、图像生成/编辑、多模态校验，按套餐(base URL+Key)分流
- 两层校验（确定性 + 多模态），错误阻断导出、警告放行
- 14 个稳定 MCP 工具 + OpenCode `/scientific-figure` 命令

## 职责边界

| 组件 | 负责 | 禁止 |
|---|---|---|
| OpenCode 规划模型 | 理解/分类/规划/总结 | 编造数据、直接出最终栅格图 |
| Ark 图像模型 | 隔离的非量化素材 | 数据图、坐标轴、数字、公式、最终复合图 |
| Ark 视觉模型 | 分析参考图/语义校验 | 从像素判断数值准确性 |
| Python | 量化图、精确几何、拼装、导出 | 编造实验值 |
| SVG | 箭头、标签、公式、规则几何 | 复杂写实设备 |

## 交付包使用指南

### 1. 准备环境

使用前需要安装：

- Python 3.11 或更高版本；
- [`uv`](https://docs.astral.sh/uv/)；
- [OpenCode](https://opencode.ai/)。

### 2. 获取交付包

下面两种方式任选一种。

方式一：使用完整仓库。在仓库根目录执行：

```bash
./install.sh
```

方式二：使用发布的源码交付包
`scientific_figure_builder-0.1.0.tar.gz`：

```bash
tar -xzf scientific_figure_builder-0.1.0.tar.gz
cd scientific_figure_builder-0.1.0
./install.sh
```

交付时应优先提供 `.tar.gz` 文件；`.whl` 文件主要用于 Python 包安装，
不是给普通用户直接运行的一键交付包。

### 3. 安装器会做什么

安装器会自动完成：

- 安装独立 Python 运行环境和火山方舟 Ark 依赖；
- 将完整 Skill 发布到 OpenCode 全局技能目录；
- 注册 `/scientific-figure` 命令；
- 安全合并 `scientific-figure` MCP 配置，不覆盖其他配置；
- 备份被修改的配置和旧版本；
- 启动 MCP 自检，确认 14 个工具均可发现。

安装过程中不会写入 API Key。安装结束后，需要完全退出并重新打开
OpenCode，让新的 Skill、命令和 MCP 配置生效。

### 4. 配置火山方舟

如果需要参考图分析、AI 素材生成或多模态校验，请在启动 OpenCode 的
终端中设置以下环境变量：

```bash
export ARK_API_KEY="<图像生成/编辑套餐 Key>"
export ARK_API_KEY_CODING="<视觉分析/校验套餐 Key>"
export ARK_IMAGE_GENERATE="<图像生成模型或 Endpoint ID>"
export ARK_IMAGE_EDIT="<图像编辑模型或 Endpoint ID>"
export ARK_VISION_ANALYZE="<视觉分析模型或 Endpoint ID>"
export ARK_VISION_VALIDATE="<视觉校验模型或 Endpoint ID>"

opencode
```

密钥只从环境变量读取，不会被写入 Skill、OpenCode 配置、运行报告或
版本库。如果只使用本地 Python/SVG 绘图，可以跳过这些变量，并使用：

```bash
./install.sh --without-ark
```

### 5. 在 OpenCode 中使用

可以直接使用自然语言：

```text
使用 scientific-figure-builder，根据 data.csv 画一张论文用折线图，
导出 PNG、SVG 和 PDF。
```

也可以使用 `/scientific-figure` 命令：

```text
/scientific-figure init
/scientific-figure plan 根据 data.csv 生成双面板科研图
/scientific-figure run
/scientific-figure resume runs/2026-07-29_figure-01
/scientific-figure validate
/scientific-figure export
```

默认工作流会先生成方案和免费 SVG 布局线框；涉及付费模型调用时，会先
等待确认。最终文件保存在版本化运行目录的 `exports/` 中。

### 6. 验证、限定项目和更新

检查现有安装：

```bash
./install.sh --verify
```

只让指定项目发现该 Skill：

```bash
./install.sh --project /path/to/project
```

更新时获取新版本仓库或解压新的交付包，然后再次执行 `./install.sh`。
安装器会替换自身文件和运行环境、更新 MCP 路径，并保留旧版本备份。

如果安装失败，安装器会返回非零状态，并尽可能恢复原运行环境；现有
OpenCode 配置在修改前会生成 `.bak` 备份。

## 开发者安装

如果只想在源码目录开发和运行测试：

```bash
cd scientific-figure-builder
uv sync
uv run pytest
```

重新生成可交付的源码包和 Python wheel：

```bash
cd ..
uv build scientific-figure-builder
# 产物位于 scientific-figure-builder/dist/
```

## 快速开始

### 初始化项目配置（无密钥）
```bash
uv run python -m figure_tools init /path/to/my-project
# 生成 .scientific-figure/{project.yaml, style_bible.json, .gitignore}
```

### 只画一张 CSV 数据图（纯本地、可复现）
```python
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec

spec = load_plot_spec("plot_spec_line.json")   # 模板见 tests/fixtures/
render_plot(spec, output_dir="out", base_dir=".")
# -> out/plot.png, out/plot.svg, out/plot.pdf, out/data_used.csv
```

### 完整图工作流（数据图 + AI 资产 + SVG 标签，自动拼装/校验/导出）
```python
from figure_tools.ark.client import ArkClient
from figure_tools.ark.real_transport import RealArkTransport   # 真实；mock 用 MockArkTransport
from figure_tools.state import Cache, RunDirectory, RunState
from figure_tools.workflow import FigureWorkflow

run_dir = RunDirectory(base_dir=".").create("figure-01")
client = ArkClient(models, RealArkTransport(), state=RunState(run_dir.name, budget=BUDGET),
                   cache=Cache(run_dir/"cache"), output_dir=run_dir)
wf = FigureWorkflow(request, config={}, run_dir=run_dir, ark_client=client,
                    state=client.state, base_dir=".", compose_dpi=300)

r = wf.run()                       # 默认先审批后执行；非 auto_execute 会暂停在 plan_approval
# r = wf.run(approved=True)        # 审批后继续
# r = wf.run(approved=True, style_anchor_approved=True)  # >=3 AI 资产时越过风格锚点
```

产出：`runs/YYYY-MM-DD_figure-XX/{plans,plots,assets,vectors,inputs,exports}/figure.{png,svg,pdf}` + `asset_manifest.json`、`style_bible.json`、`run_state.json`、`generation_report.md`。

## 源码运行时配置（真实 Ark 调用）

在 `scientific-figure-builder/.ark.env`（已 gitignore）填 6 项：
```
ARK_API_KEY=<agent 套餐 Key，图像生成/编辑>
ARK_API_KEY_CODING=<coding 套餐 Key，视觉分析/校验>
ARK_IMAGE_GENERATE=<图像生成模型/Endpoint ID，如 doubao-seedream-3-0-t2i-250415>
ARK_IMAGE_EDIT=<图像编辑模型/Endpoint ID，可与生成相同>
ARK_VISION_ANALYZE=<视觉模型/Endpoint ID，如 Doubao-1.5-vision-pro>
ARK_VISION_VALIDATE=<视觉校验模型/Endpoint ID，可与分析相同>
```
套餐按 **base URL + API Key** 路由：图像生成/编辑 -> `…/api/plan/v3`（agent 套餐）；视觉 -> `…/api/coding/v3`（coding 套餐）。

```bash
set -a && . ./.ark.env && set +a   # 然后运行你的脚本/测试
```

## OpenCode 集成

一键安装已经完成 Skill 发现、命令和 MCP 集成。重启 OpenCode 后可使用
`/scientific-figure init|plan|run|resume|validate|export`，或直接说
“使用 scientific-figure-builder 画一张……”。

## 默认安全行为

- **默认先审批后付费**：非 `auto_execute` 停在 `plan_approval`；`>=3` 个 AI 资产先生成 1 个风格锚点再暂停。
- **原始数据默认本地**，仅上传显式列出的参考图。
- **数据图走 Python/SVG，绝不走图像模型**；图像模型只产出隔离透明素材（不透明输出会做背景去除）。
- **密钥永不入库/入产物/入日志**。

## 测试

```bash
uv run pytest                                                  # 全量（真实用例无凭据时跳过）
set -a && . ./.ark.env && set +a && uv run pytest tests/e2e    # 真实付费验收（3 个用例）
```

## 项目结构

```
scientific-figure-builder/
├── SKILL.md                 # OpenCode 技能定义
├── schemas/                 # 6 个版本化 JSON Schema
├── references/              # 路由/工作流/Ark 接口/输出契约/领域模板
├── templates/               # 默认 project.yaml、style_bible、mplstyle、plot-recipes
├── figure_tools/            # Python 核心
│   ├── ark/                 # Ark client + transport（mock/real）+ 背景去除
│   ├── planning/            # 任务路由 + figure-plan 生成
│   ├── plotting/            # spec/data/recipes/renderer
│   ├── vector/              # SVG 原语 + LaTeX->SVG + 线框 + 归一化
│   ├── imaging/             # 背景去除（透明度工作流）
│   ├── validation/          # 图像/数据/最终校验 + summary
│   ├── assembly/            # 合成器
│   ├── export/              # PNG/SVG/PDF/PPTX 导出
│   ├── config.py state.py orchestrator.py workflow.py report.py server.py
├── install.sh              # 一键安装入口
├── install/                 # 交付安装器 + 安全 OpenCode 配置合并器
├── commands/                # /scientific-figure 命令定义
└── tests/                   # unit / integration / e2e
```

## 状态

v1（Phase 1-7）已完成并通过真实模型验收。3 个真实付费用例通过：CSV->可复现出版图；参考图分解->透明资产->重构；混合多面板（AI 资产 + Python 图 + SVG 标签）。

排除项（不在 v1 内）：Blender、动画、交互式 web 可视化、可旋转 3D、非火山方舟的 provider、整篇论文 PDF 解析、一次性生成正式复合图、色盲等无障碍检查。

## 贡献

欢迎通过 Issue 和 Pull Request 报告问题或改进项目。开始前请阅读
[`CONTRIBUTING.md`](./CONTRIBUTING.md)；安全问题请遵循
[`SECURITY.md`](./SECURITY.md) 中的私密报告流程。

## 引用

如果本项目对你的研究有帮助，请使用 [`CITATION.cff`](./CITATION.cff)
提供的元数据进行引用。创建正式版本后，可将发布版本和 DOI 补充到引用信息中。

## License

本项目采用 [MIT License](./LICENSE)。
