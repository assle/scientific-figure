# Agent Constraints

These constraints are loaded by default on every execution.

## Avoid Overengineering

Implement the smallest correct change that satisfies the explicit request.

Do not add abstractions, fallback logic, defensive checks, compatibility layers,
configuration, refactors, or future-proofing for hypothetical requirements. Only
introduce additional complexity when it is required for correctness, security, or
by an established pattern in the existing codebase.

When multiple implementations are valid, prefer the simplest one with the smallest
diff.

## Incremental Development

Keep understanding, decomposition, and implementation choices with the user. Treat a concrete
change the user has already selected as the current increment. When a request is exploratory or
spans multiple changes, inspect the existing code, explain the smallest coherent next change, and
wait for the user to choose before editing.

Implement only the selected increment. Include its mechanically necessary tests and documentation,
verify the observable result, report what changed, and stop before starting another increment.

Before ending an increment that changed workspace files, inspect the actual diff and use the CI/CD
command index below. Give the user the exact applicable verification and delivery commands, state
whether the next action is push/PR only, local source activation, or a Product release, and justify
that classification from the changed files (for example, repository docs versus Core or shipped
workflow resources).

Treat newly discovered knowledge, terminology, constraints, and follow-up work as decision points,
not implicit requirements. Explain them in plain language and how they affect the current choice;
do not silently expand the scope, rewrite the requirement, or turn them into a complete upfront spec.

This is the default for non-trivial coding work. If the user explicitly requests end-to-end
implementation or invokes a workflow skill, follow that requested scope or workflow instead.

## Language

- **User-facing interaction**: Always communicate with the user in Chinese (中文).
- **Background operations**: All call chains, prompts, execution chains, and internal logs must use English for clarity and consistency.

## Project references

### Issue tracker

Issues and PRDs live as GitHub issues, managed through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

### CI/CD commands

For documentation-only, test/CI, Core or installer, Skill/Schema/template, local source activation,
and patch/minor release changes, follow `docs/operations/ci-cd-commands.md`.

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
