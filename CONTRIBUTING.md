# 贡献指南

感谢你愿意改进 Scientific Figure Builder。

## 开始之前

- 不要提交 API Key、真实凭据、未公开论文数据或无权再分发的素材。
- 功能变更应保持“数据图由 Python/SVG 确定性生成，图像模型按已确认的生成单元生成非量化内容”这一职责边界。
- 真实 Ark 测试会产生费用；普通贡献不应依赖真实凭据或付费调用。

## 本地开发

需要 Python 3.11 或更高版本以及 [uv](https://docs.astral.sh/uv/)。

```bash
cd scientific-figure-builder
uv sync
uv run pytest
```

没有 Ark 凭据时，真实端到端用例会自动跳过。只有在明确需要验证真实模型集成、了解费用并使用自己的凭据时，才运行付费验收测试。

## 提交变更

1. 从 `main` 创建一个主题分支。
2. 保持改动聚焦，并为行为变化添加或更新测试。
3. 运行完整测试，确认没有把生成产物、本地环境或凭据加入版本控制。
4. 在 Pull Request 中说明问题、解决方式、验证结果和任何兼容性影响。

提交贡献即表示你同意按照本项目的 [MIT License](./LICENSE) 授权该贡献。

## 版本与发布

项目遵循语义化版本，当前处于 `0.y.z` 的 1.0 前开发阶段。
`scientific-figure-builder/pyproject.toml` 中的 `project.version` 是 Product version
的唯一权威来源。`SKILL.md` 和 `CITATION.cff` 中的版本是发布元数据镜像，测试会阻止
它们与 Product version 不一致；运行时 Python 包、CLI 和 MCP 服务不得再维护独立的
硬编码版本。

- 向后兼容的修复使用 patch 版本。
- 向后兼容的新能力使用 minor 版本。
- 1.0 前无法保持兼容的变更使用 minor 版本，并在发布说明中明确迁移方式。
- 1.0 后不兼容的公开契约变更使用 major 版本。

需要发布的功能修改应先正常提交到 `main`，然后运行：

```bash
python3 scripts/release.py patch --publish
```

脚本在隔离 worktree 中生成版本提交，推送后等待权威 CI，通过后才创建不可变 tag；tag
workflow 构建完整 Product bundle、Core wheel、Release manifest 和校验摘要，并创建
GitHub Release。详细的本地激活、宿主重载、退出码和兼容入口见
[发布与本地更新](docs/operations/release-and-local-activation.md)。

Schema version、Phase prompt version 和 recipe version 是独立兼容性契约，不能因为
Product version 变化而自动递增。
