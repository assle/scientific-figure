# CI/CD 命令手册

本手册是维护 Scientific Figure Builder 时选择验证、提交、发布和本地更新命令的唯一入口。
发布、本地激活和 Codex 重载的职责边界见
[发布与本地更新](release-and-local-activation.md)。

## 先判断修改类型

| 修改范围 | 本地验证 | Product release |
|---|---|---|
| `README*`、`docs/`、`SECURITY.md`、`CONTRIBUTING.md` | `git diff --check` | 不需要 |
| `tests/`、`.github/workflows/`、仅维护者使用的 `scripts/` | 完整候选验证 | 通常不需要 |
| `figure_tools/`、`install/`、根安装与卸载脚本 | 完整候选验证 | patch 或 minor |
| `SKILL.md`、`agents/`、`schemas/`、`templates/` | 同步插件后完整候选验证 | patch 或 minor |
| `plugins/` | 不直接编辑；从规范源同步 | 随规范源发布 |

兼容修复和不改变公开契约的行为修正使用 patch。新增能力、Schema 契约或 1.0 前不兼容修改
使用 minor。只修改仓库文档、测试或 CI 时不递增 Product version。

## 开始修改

稳定流程使用主题分支和 Pull Request：

```bash
cd /Users/assle/dev/scientific-figure
git switch main
git pull --ff-only
git switch -c codex/update-documentation
```

## 只修改普通文档

```bash
git diff --check
git add README.md README.zh-CN.md docs SECURITY.md CONTRIBUTING.md
git diff --cached --check
git commit -m "Update documentation"
git push -u origin HEAD
gh pr create --fill
gh pr checks --watch
```

普通文档合并后流程结束，不构建新 Product version，也不重新安装本机 Runtime。

## 修改测试、CI 或维护脚本

先运行受影响的聚焦测试，再执行完整候选验证：

```bash
python3 scripts/verify_release_candidate.py --tests --build
```

依赖已经缓存但外部包索引暂时不可用时：

```bash
UV_OFFLINE=1 python3 scripts/verify_release_candidate.py --tests --build
```

提交并等待 PR CI：

```bash
git add scientific-figure-builder/tests .github/workflows scripts
git diff --cached --check
git commit -m "Improve CI coverage"
git push -u origin HEAD
gh pr create --fill
gh pr checks --watch
```

仅测试和 CI 行为变化不发布 Product version。若改动同时改变安装器、Release artifact 或用户
运行行为，按代码修改处理。

## 修改 Core、安装器或 CLI

完整候选验证是提交前门禁：

```bash
python3 scripts/verify_release_candidate.py --tests --build
```

提交时只暂存本次修改：

```bash
git add \
  scientific-figure-builder/figure_tools \
  scientific-figure-builder/install \
  scientific-figure-builder/tests \
  install.sh \
  uninstall.sh
git diff --cached --check
git commit -m "Fix Scientific Figure Builder runtime"
git push -u origin HEAD
gh pr create --fill
gh pr checks --watch
```

修复使用 patch；新增用户可见能力或不兼容契约使用 minor。

## 修改 Skill、Agent、Schema 或模板

这些目录是插件快照的规范源。先同步，再验证：

```bash
python3 scripts/sync_plugin_bundle.py
python3 scripts/verify_release_candidate.py --tests --build
```

规范源与生成快照必须在同一提交：

```bash
git add \
  scientific-figure-builder/SKILL.md \
  scientific-figure-builder/agents \
  scientific-figure-builder/schemas \
  scientific-figure-builder/templates \
  plugins
git diff --cached --check
git commit -m "Update Scientific Figure Builder workflow resources"
git push -u origin HEAD
gh pr create --fill
gh pr checks --watch
```

## 在本机试用未发布 Core

只更新 Core runtime 和可选 Configuration app：

```bash
python3 scripts/verify_release_candidate.py --tests --build
./install.sh --runtime-only --with-gui
```

完全退出并重新打开 Codex，然后检查：

```bash
/Users/assle/.local/bin/scientific-figure status --verbose
```

`--runtime-only` 不更新 Native plugin 或其 Workflow Skill。修改插件、Skill、Schema 或模板后，
使用正式发布流程验证完整交付。

## 合并后检查 main CI

```bash
git switch main
git pull --ff-only
gh run list \
  --commit "$(git rev-parse HEAD)" \
  --workflow Tests \
  --limit 1
```

取得 run ID 后等待权威结果：

```bash
RUN_ID=$(gh run list \
  --commit "$(git rev-parse HEAD)" \
  --workflow Tests \
  --limit 1 \
  --json databaseId \
  --jq '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
```

main CI 未成功时只修复并重新推送；此时不创建 tag，不运行正式发布命令。

## 发布 patch

例如从 `0.6.0` 发布 `0.6.1`，先设置版本并创建发布说明：

```bash
NEXT_VERSION=0.6.1
touch "release-notes/$NEXT_VERSION.md"
open -a TextEdit "release-notes/$NEXT_VERSION.md"
```

发布说明格式：

```markdown
---
status: approved
---

# Scientific Figure Builder 0.6.1

## Changes

- Describe the fixes.

## Verification

- Full CI matrix passed.
```

main CI 成功后执行：

```bash
NEXT_VERSION=0.6.1
python3 scripts/release.py patch \
  --publish \
  --notes-file "$PWD/release-notes/$NEXT_VERSION.md" \
  --activate-local
```

## 发布 minor

例如从 `0.6.x` 发布 `0.7.0`：

```bash
NEXT_VERSION=0.7.0
touch "release-notes/$NEXT_VERSION.md"
open -a TextEdit "release-notes/$NEXT_VERSION.md"
python3 scripts/release.py minor \
  --publish \
  --notes-file "$PWD/release-notes/$NEXT_VERSION.md" \
  --activate-local
```

只准备隔离候选、不推送时省略 `--publish`：

```bash
python3 scripts/release.py patch
```

## 发布失败后继续

发布脚本报告 main CI 失败时，先读取对应 Actions run，修复后提交并等待新 main CI。新 commit
成功后重复原发布命令；发布器会选择当前 `HEAD`。不可移动或覆盖已经存在的 tag。

## 发布完成检查

```bash
RELEASE_VERSION=0.6.1
python3 scripts/release.py "$RELEASE_VERSION" --check-release
gh release view "v$RELEASE_VERSION"
/Users/assle/.local/bin/scientific-figure status --verbose
```

`--activate-local` 返回 `2` 表示 Release 已成功，但本机仍有旧 MCP/GUI 进程。保存工作、完全
重启 Codex，再运行 `status --verbose`，直到状态为 `converged`。
