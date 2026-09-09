---
name: scientific-figure-builder
description: Route scientific-figure requests through the Scientific Figure Builder lifecycle. Use it to plan, generate, validate, repair, resume, or export figures with deterministic, image, or multimodal providers.
license: MIT
metadata:
  version: "0.6.0"
  provider: configurable
  scope: product-component
---

# Scientific Figure Builder

## Lifecycle router

Use `advance_figure_workflow` as the single entry point for normal figure work.
Submit the user's request, approval, correction, or resume action, then treat the
returned `phase`, `status`, and `next_action` as authoritative.

- For `status: paused`, surface the requested clarification, approval,
  `generation_summary`, error, or recovery information. Submit the user's answer
  as the corresponding action. Display every `generation_summary` before image
  generation continues; a summary is not a completed figure.
- For `status: in_progress`, resume the same operation with its returned
  `operation_id` until the state changes. Surface an unknown remote outcome
  instead of starting a replacement operation.
- For `status: completed`, report the returned artifacts. Stop when
  `next_action` is null.
- When `next_action` is `resume` and no user input is requested, resume directly.
  Perform only the action identified by `next_action`.

## User intent

Translate explicit generation choices into `request.generation_intent` and
preserve their method, scope, membership, ownership, background, and required
content. A later explicit user instruction authorizes
`revise_generation_intent`; ask only for information that remains ambiguous.

## Runtime authority

The Runtime owns phase transitions, deterministic planning, generation routes,
budgets, provider capabilities, repair eligibility, validation, and export
gates. Use its versioned artifacts as the handoff between phases and correct
invalid input only through the action it requests.

Keep normal lifecycle work inside the orchestrator: do not sequence low-level
generation or assembly tools, create ad-hoc substitutes, bypass a blocked gate,
or replace an active operation. Before a network operation uploads local raw
CSV, Excel, or JSON data, disclose what will be sent.
