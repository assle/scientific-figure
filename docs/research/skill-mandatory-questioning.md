# How Codex Skills Get the Model to Ask Before Acting

## Question

Why do `grilling` / `grill-with-docs` reliably ask the user a question every
time they are invoked, while `scientific-figure-builder` keeps skipping the
clarification questions and going straight to script generation? What should
`scientific-figure-builder` copy?

## Primary findings

### 1. The working skills make interviewing the *entire* task

`/Users/assle/.codex/skills/grilling/SKILL.md` has no generation workflow. Its
body is a short, imperative interview:

> Interview me relentlessly about every aspect of this until we reach a shared
> understanding. ... Ask the questions one at a time, waiting for feedback on
> each question before continuing. ... Do not act on it until I confirm we have
> reached a shared understanding.

Because there is nothing else to do, the model has no "execute" path to fall
back to. This is the core working mechanism.

### 2. The router skills force that interview skill

`/Users/assle/.codex/skills/grill-me/SKILL.md` and
`/Users/assle/.codex/skills/grill-with-docs/SKILL.md` do not contain a workflow;
they delegate:

```text
Run a `/grilling` session.
```

`grill-with-docs` additionally delegates to `/domain-modeling`, but the first
and only entry point is still the interview session. This router pattern is
what makes "every invocation asks" reliable.

### 3. They disable implicit invocation

`/Users/assle/.codex/skills/grill-with-docs/SKILL.md` has:

```yaml
disable-model-invocation: true
```

and `/Users/assle/.codex/skills/grill-with-docs/agents/openai.yaml` has:

```yaml
policy:
  allow_implicit_invocation: false
```

So the skill is only used when the user explicitly asks for it; it is not
merged into an unrelated coding task where Default-mode execution bias would
override its instruction.

### 4. `scientific-figure-builder` is the opposite shape

`/Users/assle/.codex/skills/scientific-figure-builder/SKILL.md` mixes a short
ask-first block with a long generation workflow. The model reads the overall
goal ("produce figures") and, in Default mode, chooses the execution path.
Its `agents/openai.yaml` now has a `default_prompt`, but no
`policy.allow_implicit_invocation: false`.

## Codex enforcement boundaries

- Skill frontmatter is **prompt guidance, not a permission boundary** in Codex.
  `allowed-tools` is not enforced as a strict allowlist.
  Source: `openai/skills` migration note
  ("allowed-tools | No strict skill allowlist | Preserved as prompt guidance").
- `PreToolUse` hooks currently intercept only the `Bash` tool; file-write and
  MCP tool calls do not fire it.
  Source: Codex hooks community reference
  (https://symposium.dev/design/agent-details/codex-cli.html).
- Plan mode is the product path designed for clarify-before-execute; it is
  toggled by the user, not by a skill.
  Source: Codex manual notes `/plan`
  (https://developers.openai.com/codex/codex-manual.md).

## Recommendations for `scientific-figure-builder`

1. **Adopt the router pattern**: make the top of `SKILL.md` run a mandatory
   interview session before any figure work, phrased exactly like `grilling`
   ("Ask one question at a time and wait; do not act until all four are
   answered").
2. **Keep the interview block short and non-negotiable**, and put the long
   generation workflow in a separate reference/phase that is only entered after
   confirmation.
3. **Disable implicit invocation** so the skill is only entered explicitly via
   `$scientific-figure-builder`, matching `grill-with-docs`.
4. **Keep `agents/openai.yaml.default_prompt`** starting with the ask-first
   instruction; it is inserted on `$` invocation.
5. **Do not rely on `allowed-tools`** as enforcement in Codex. If a hard backstop
   is still needed, use Plan mode or a Bash-only `PreToolUse` hook.

## Sources

- `/Users/assle/.codex/skills/grilling/SKILL.md`
- `/Users/assle/.codex/skills/grill-me/SKILL.md`
- `/Users/assle/.codex/skills/grill-with-docs/SKILL.md`
- `/Users/assle/.codex/skills/grill-with-docs/agents/openai.yaml`
- `/Users/assle/.codex/skills/scientific-figure-builder/SKILL.md`
- `/Users/assle/.codex/skills/scientific-figure-builder/agents/openai.yaml`
- `openai/skills` Codex migration note: `allowed-tools` is prompt guidance only
- Codex hooks community reference:
  https://symposium.dev/design/agent-details/codex-cli.html
- Codex manual `/plan`:
  https://developers.openai.com/codex/codex-manual.md
