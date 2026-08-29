# Mission: Scientific Figure Builder

## Why
为科研工作者和 AI Coding Agent 提供一个开源、可复现、可审计的科研绘图产品，能够干净安装、可靠运行、明确控制付费模型调用，并在卸载时不损坏用户配置和凭据。

## Success looks like
- 产品组件具有明确边界：工作流 Skill、生命周期 MCP 服务、核心运行时、CLI、配置应用和 Agent 集成各自只有一个职责。
- Codex 和 OpenCode 用户能够完成“先澄清、再审计划、再付费生成、最后验证与导出”的完整任务。
- 安装、验证、升级和卸载共享同一套路径与版本规则，不遗留无主运行时或宿主配置。
- API Key 不进入项目文件、日志、产物或 Agent 配置，付费调用始终受审批和预算约束。
- Product version、Schema version、Phase prompt version 和 recipe version 各自具有清晰兼容性语义。

## Current delivery
- 当前开发版本为 `0.1.0`，处于 1.0 前的接口稳定化阶段。
- 当前交付物是 Codex/OpenCode Agent 集成包，不是原生 Codex 插件。
- 原生插件是目标交付形态；它将标准化 Skill、MCP、资源和宿主管理的生命周期。

## Constraints
- Provider 保持可配置，不把任何模型供应商设为内置默认。
- 精确数据、文字、公式和布局继续使用确定性本地路径；图像模型只生成或修复合格的非量化栅格素材。
- 用户项目保留在用户选择的位置，凭据保留在系统凭据存储中。
