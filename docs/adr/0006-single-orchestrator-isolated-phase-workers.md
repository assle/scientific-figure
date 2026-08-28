---
status: accepted
---

# Use one orchestrator with isolated phase workers

Scientific Figure Builder will use one code-owned Orchestrator as the authority
for its workflow lifecycle. Model-assisted reasoning will run in isolated Phase
workers with phase-specific prompts and allowed tools, while versioned Phase
artifacts, rather than a long-lived conversation context, carry decisions into
downstream phases. This gives the Calling Agent one stable workflow interface
and keeps phase transitions, approvals, budgets, retries, resume behavior, and
artifact invalidation in one implementation.

When a `phase_reasoning` Model route is configured, each worker uses one fresh
Provider call. Offline runs use a schema-equivalent deterministic worker rather
than returning control to a long-lived Calling Agent prompt.

The Lifecycle phases are Intake, Planning, Execution, Review and repair, and
Export. Python plotting, SVG rendering, image generation, image editing, and
assembly remain Generation routes inside Execution rather than becoming
separate Lifecycle phases. Export remains deterministic during normal
operation and does not require a Phase worker.

## Considered options

- **One long-lived Calling Agent prompt** — rejected because phase instructions
  accumulate in one context, approved decisions can be reinterpreted, workflow
  state remains partly implicit, and tool ordering is difficult to enforce or
  test through one stable interface.
- **Multiple autonomous Agents** — rejected because distributing phase
  authority introduces coordination, state-ownership, approval, and
  reproducibility problems that the figure workflow does not need.
- **One Orchestrator with isolated Phase workers and Phase artifacts (chosen)**
  — concentrates workflow authority while giving each reasoning phase a fresh,
  minimal context and an explicit schema-governed handoff.

## Consequences

Calling Agent commands become adapters to the same Orchestrator rather than
independent owners of workflow sequencing. A Phase worker may return only its
schema-valid Phase artifact; it may not advance Run state or write arbitrary
downstream outputs. The Figure brief becomes the authoritative output of
Intake, and each later Phase artifact references the exact upstream version or
hash it consumed.

Existing Provider-neutral Model routing, deterministic validation authority,
Configuration app scope, and Export gate decisions remain in force. The
detailed implementation and testing contract is tracked in
[Issue #17](https://github.com/assle/scientific-figure/issues/17).
