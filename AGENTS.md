# Agent Constraints

These constraints are loaded by default on every execution.

## Language

- **User-facing interaction**: Always communicate with the user in Chinese (中文).
- **Background operations**: All call chains, prompts, execution chains, and internal logs must use English for clarity and consistency.

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues, managed through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.
