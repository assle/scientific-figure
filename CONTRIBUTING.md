# 贡献指南

感谢你愿意改进 Scientific Figure Builder。

## 开始之前

- 不要提交 API Key、真实凭据、未公开论文数据或无权再分发的素材。
- 功能变更应保持“数据图由 Python/SVG 确定性生成，图像模型按已确认的生成单元生成非量化内容”这一职责边界。
- 真实 Provider 验收测试会产生费用；普通贡献不应依赖真实凭据或付费调用。

## 本地开发

需要 Python 3.11 或更高版本以及 [uv](https://docs.astral.sh/uv/)。

```bash
cd scientific-figure-builder
uv run --frozen pytest
python3 ../scripts/verify_release_candidate.py --build
```

付费 Provider 和桌面 PowerPoint 验收用例默认跳过。只有在明确需要验证对应集成、了解费用或桌面副作用，并使用自己的凭据和环境时，才启用这些测试。

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

需要发布的功能修改应先正常提交到 `main`。只准备本地候选版本、不发布时运行：

```bash
python3 scripts/release.py patch
```

正式发布时，应先准备包含 `status: approved` 的 Release notes，然后直接运行
`python3 scripts/release.py patch --publish --notes-file FILE`。发布流程在隔离 worktree
中生成版本提交，推送后等待权威 CI，通过后才创建不可变 tag。Tag workflow 构建完整
Product bundle、Core wheel、Release manifest 和校验摘要，并创建 GitHub Release。
发布成功后如需在本机试用，用 `./install.sh --codex --release vVERSION` 激活，保存工作后
完全重启 Codex，再运行 `scientific-figure status --verbose` 直到状态为 `converged`。

Schema version、Phase prompt version 和 recipe version 是独立兼容性契约，不能因为
Product version 变化而自动递增。
