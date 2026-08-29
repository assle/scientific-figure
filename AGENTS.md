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

## Filesystem layout

- Follow the XDG Base Directory Specification for per-user configuration, data,
  state, cache, and session runtime files. Honor absolute XDG overrides, use the
  standard defaults, and keep each category in an application subdirectory.
- Use `$HOME/.local/bin` only for per-user launchers. XDG does not define an
  application-payload location; keep code, private runtimes, virtual
  environments, and dependencies out of `XDG_DATA_HOME` and use a documented,
  platform-appropriate installation prefix.
- Share path resolution across install, verify, upgrade, runtime, and uninstall.
  Keep user projects in user-selected locations and secrets in the OS credential
  store; update tests, docs, migration, and cleanup together when paths change.
