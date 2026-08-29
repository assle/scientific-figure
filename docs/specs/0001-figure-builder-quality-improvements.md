---
status: draft
created: 2026-07-29
seam: advance_figure_workflow (lifecycle integration)
adr: 0001-current-evidence-figure-set
---

# Spec: Scientific Figure Builder 质量改进

## Problem Statement

在使用 scientific-figure-builder 制作梯形光栅效率研究的三张数据图时，反复出现图例与数据重叠、面板宽度分配不合理、视觉校验未能发现布局问题等质量缺陷。具体表现：

1. 视觉模型的默认校验提示词只检查"对象数量、结构、透视、禁止内容、风格一致性"，不检查图例与数据的重叠、文字重叠、标签可读性等布局问题，导致视觉模型反复报 pass 而用户反复发现重叠。
2. 渲染前没有任何布局分析步骤，面板宽度比例和图例位置完全靠人工经验决定，容易出现"面板太窄放不下图例"的根因问题。
3. 校验非强制，可以跳过校验直接导出，没有门禁机制阻止未校验的图流出。
4. 校验发现问题时，直接报告症状（如"图例重叠"），不分析根因（如"面板宽度比例不合理"），导致修标不修本，反复在症状层面打补丁。

## Solution

在 scientific-figure-builder 的工作流中增加四个质量保障环节：

1. **扩展校验提示词**：在默认视觉校验提示词中加入图例-数据重叠、文字重叠、标签可读性检查项，使视觉模型能主动发现布局问题。
2. **渲染前布局分析**：在渲染前用 Python 程序化分析数据分布，输出面板宽度比例建议、图例候选位置的数据密度报告，作为渲染参数的依据。
3. **强制校验门禁**：export 步骤前检查 validation_report.json 是否存在且非阻塞，缺失或阻塞时拒绝导出。
4. **根因分析流程**：校验发现 fail 项时，自动生成根因分析报告，列出可能的结构性原因（如"面板宽度不足""图例位置与数据高密度区重合"），而非仅报告症状。

## User Stories

### 校验提示词改进

1. As a figure builder user, I want the vision validation to check whether legends overlap with data elements, so that legend-data overlap is caught before export.
2. As a figure builder user, I want the vision validation to check whether any text elements overlap with each other, so that text collision is caught before export.
3. As a figure builder user, I want the vision validation to check whether axis tick labels are readable and not overlapping, so that label crowding is caught before export.
4. As a figure builder user, I want the validation report to include a specific check item named "legend_data_overlap" with pass/fail status and detail, so that I can see exactly which panel has the overlap problem.
5. As a figure builder user, I want the validation prompt to remain concise enough that the vision model responds within a reasonable timeout, so that validation does not stall indefinitely.

### 渲染前布局分析

6. As a figure builder user, I want the planner to analyze data density across candidate legend positions before rendering, so that the legend is placed in the emptiest region of the plot.
7. As a figure builder user, I want the planner to recommend panel width ratios based on the number of data elements per panel, so that panels with more data elements get proportionally more width.
8. As a figure builder user, I want the layout analysis to output a machine-readable report (JSON) with density scores per region and recommended placements, so that I can review the reasoning before rendering.
9. As a figure builder user, I want the layout analysis to consider label text length when computing panel width recommendations, so that panels with long tick labels get enough space.
10. As a figure builder user, I want the layout analysis to flag when a panel has too many data elements for its allocated width and no viable in-plot legend position exists, so that I know to use an external legend or adjust the layout.

### 强制校验门禁

11. As a figure builder user, I want the export step to refuse to produce final outputs if no validation report exists, so that unvalidated figures cannot be exported.
12. As a figure builder user, I want the export step to refuse to produce final outputs if the validation report contains any blocking errors, so that figures with known quality issues cannot be exported.
13. As a figure builder user, I want the export step to produce a clear error message explaining why export was blocked, so that I know what to fix.
14. As a figure builder user, I want the validation gate to check for both per-asset validation reports and the final assembled-figure validation report, so that all validation layers are confirmed before export.
15. As a figure builder user, I want to be able to override the gate with an explicit force flag when I understand the risks, so that I am not permanently blocked by a non-critical issue.

### 根因分析流程

16. As a figure builder user, I want the workflow to produce a root cause analysis when any validation check fails, so that I can fix the underlying problem instead of the symptom.
17. As a figure builder user, I want the root cause analysis to identify structural causes such as "panel width insufficient for data element count" or "legend position overlaps high-density data region", so that I know whether to adjust layout, resize panels, or move the legend.
18. As a figure builder user, I want the root cause analysis to suggest specific remediation actions (e.g., "increase panel c width ratio from 1.1 to 1.5" or "move legend to lower-right where data density is 1/12"), so that I can act on the analysis directly.
19. As a figure builder user, I want the root cause analysis to be saved as a JSON file in the run directory alongside the validation report, so that it is preserved for auditability.
20. As a figure builder user, I want the root cause analysis to run automatically after validation without requiring a separate command, so that I always get analysis when problems are found.

## Implementation Decisions

### 1. 校验提示词改进

- 修改 `real_transport.py` 中 `_vision` 方法的默认 validation instruction，在现有检查项后追加三个布局检查项：`legend_data_overlap`、`text_overlap`、`label_readability`。
- 追加的提示词保持简洁（每项一句描述），避免因提示词过长导致视觉模型超时。
- `validate_image_asset` 返回的 checks 列表中应包含这三个新 check_id，状态为 pass 或 fail。
- 不修改确定性检查（`deterministic_image_checks`），布局重叠检查仅由视觉模型承担。

### 2. 渲染前布局分析

- 新增 `figure_tools/planning/layout_analysis.py` 模块。
- 该模块导出一个函数 `analyze_layout(figure_plan, data_characteristics) -> LayoutReport`，其中 `data_characteristics` 描述每个面板的数据元素数量、标签长度、数据范围等。
- `LayoutReport` 包含：
  - `panel_width_recommendations`: 基于数据元素数量推荐的宽度比例
  - `legend_placement_recommendations`: 每个需要图例的面板的候选位置及数据密度评分
  - `warnings`: 面板宽度不足、无可行图例位置等警告
- 该函数为纯函数，不调用任何外部服务，无副作用。
- Orchestrator 在 Planning 产出 Figure plan 后调用 Figure Execution Module 生成该报告，并写入 `plans/layout_analysis.json`。
- 该报告为建议性质，不自动覆盖用户指定的布局参数，但会在 wireframe 和 plan 旁边展示供参考。

### 3. 强制校验门禁

- 在 Figure Execution Module 的 publish Interface 中执行校验门禁检查：
  - 检查 `validation_reports` 列表非空（至少包含 per-asset 和 final validation）
  - 检查所有 report 的 `summary.blocking` 为 False
  - 如果检查失败，设置 `exported = False` 并在返回值中添加 `export_blocked_reason`
- 同时在 MCP server 的 `_h_export_figure` handler 中增加对 `validation/validation_report.json` 存在性的检查。
- 支持 `force_export=True` 参数绕过门禁，但会在 generation_report 中记录绕过行为。

### 4. 根因分析流程

- 新增 `figure_tools/validation/root_cause.py` 模块。
- 该模块导出一个函数 `analyze_root_causes(validation_reports, figure_plan, layout_analysis) -> RootCauseReport`。
- `RootCauseReport` 包含：
  - `findings`: 列表，每项包含 `symptom`（验证失败项的 check_id 和 detail）、`likely_cause`（结构性原因）、`remediation`（具体建议）
  - `severity_ranking`: 按影响程度排序的根因列表
- 根因分析规则基于模式匹配，例如：
  - `legend_data_overlap` + 面板宽度比例差异大 -> "面板宽度不足以容纳图例"
  - `effective_dpi` fail -> "bbox_inches=tight 导致 DPI 下降，建议提高 savefig dpi"
  - `text_overlap` + 标签长度 > 面板宽度 -> "标签过长，建议缩写或分两行"
- Figure Execution Module 在最终验证存在 blocking 或 fail 项时调用此函数，并将报告写入 `validation/root_cause_report.json`。

### Schema 变更

- `validation-report.schema.json` 的 `checks` 列表新增三个可选 check_id：`legend_data_overlap`、`text_overlap`、`label_readability`。这些是约定名称，不需要 schema 强制。
- 新增 `layout-analysis.schema.json`（schema_version "1.0"）。
- 新增 `root-cause-report.schema.json`（schema_version "1.0"）。

### API 合约

- `analyze_layout(figure_plan, data_characteristics) -> LayoutReport`：纯函数，输入 figure_plan dict 和 data_characteristics dict，输出 LayoutReport dict。
- `analyze_root_causes(validation_reports, figure_plan, layout_analysis) -> RootCauseReport`：纯函数，输入验证报告列表、figure_plan 和可选的 layout_analysis，输出 RootCauseReport dict。

## Testing Decisions

### 集成 seam：advance_figure_workflow

- 在 `tests/integration/test_workflow.py` 中新增测试用例：
  - 测试渲染前生成了 `plans/layout_analysis.json`
  - 测试校验报告中包含 `legend_data_overlap` 等 check_id
  - 测试当 validation blocking 时 export 被阻止
  - 测试当 validation 有 fail 项时生成了 `validation/root_cause_report.json`
- 使用 MockProviderTransport 注入预设的验证结果，不依赖真实供应商服务。

### 单元测试

- `tests/unit/test_real_transport.py`：测试修改后的 `_vision` 方法返回的 checks 包含布局检查项。使用 mock transport。
- `tests/unit/test_planning.py`：测试 `analyze_layout` 函数在不同数据特征下输出合理的宽度比例和图例位置建议。
- `tests/unit/test_final_checks.py`：测试校验门禁逻辑——缺失 validation report 时阻止导出。
- 新增 `tests/unit/test_root_cause.py`：测试 `analyze_root_causes` 函数对常见失败模式的根因识别。

### 测试原则

- 只测试 external behavior（函数输入输出），不测试 implementation details。
- 布局分析测试用构造的 figure_plan 和 data_characteristics，不依赖真实数据文件。
- 根因分析测试用构造的 validation_reports，不依赖真实验证结果。
- 校验提示词测试验证返回的 checks 包含预期的 check_id，不验证提示词的具体文字。

## Out of Scope

- 不修改 MCP tool schema 以暴露 project_dir 等参数（这是独立的工具层问题）。
- 不解决 Ark 视觉模型服务超时的根本原因（这是外部服务可靠性问题）。
- 不实现自动修复——根因分析只提供建议，不自动调整布局参数或重新渲染。
- 不修改已有的 figure_plan.schema.json 结构（布局分析报告是独立文件）。
- 不增加新的付费调用——布局分析和根因分析都是纯 Python，不调用 Ark 模型。

## Further Notes

- 本 spec 基于本会话中制作梯形光栅效率研究五张数据图时的实际经验。核心教训是：症状层面的修复（移动图例位置）会引入新症状（新位置又重叠），只有根因层面的修复（调整面板宽度比例）才能终止循环。四个改进共同构成一个"分析-渲染-校验-根因"的质量闭环。
- 改进优先级建议：3（门禁）> 1（提示词）> 2（布局分析）> 5（根因分析）。门禁是最低成本的改进（防止未校验图流出），提示词改进是最高收益的改进（让校验真正发现布局问题），布局分析是预防性改进（在渲染前避免问题），根因分析是辅助性改进（帮助定位问题）。
