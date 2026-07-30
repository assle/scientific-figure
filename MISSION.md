# Mission: 在 OpenCode 中使用 Scientific Figure Builder

## Why
能够在真实论文项目中，从 OpenCode 发起科研图规划、审批、生成、验证和导出，并正确使用火山方舟模型而不泄露密钥或误触发付费调用。

## Success looks like
- 能把 Skill、命令和 MCP 正确接入 OpenCode
- 能区分 `init`、`plan`、`run`、`resume`、`validate` 和 `export`
- 能完成一次“先审计划、再付费生成、最后导出”的完整任务
- 能定位 MCP 未连接、环境变量未加载和命令未发现等常见问题

## Constraints
- 当前实现位于仓库中的 `scientific-figure-builder/`
- 使用 OpenCode 1.18.8、`uv` 和现有 `.ark.env`
- API Key 不写入 OpenCode 配置、项目配置或教学材料

## Out of scope
- 修改 Scientific Figure Builder 的实现
- 更换火山方舟模型供应商
- 扩展 Blender、动画或交互式绘图能力
