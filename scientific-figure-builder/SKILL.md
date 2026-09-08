---
name: scientific-figure-builder
description: Workflow Skill for the Scientific Figure Builder product. Use it to turn a scientific-figure request into a governed lifecycle, route work to deterministic plots, SVG, and configured image or multimodal providers, validate results, and export publication-ready PNG/SVG/PDF. Not a single-prompt image generator. Works with OpenCode and Codex.
license: MIT
metadata:
  version: "0.4.0"
  provider: configurable
  scope: product-component
---

# Scientific Figure Builder

## Lifecycle router

The Calling Agent submits user input, approvals, or resume actions to the
single `advance_figure_workflow` orchestrator tool. Read its returned
`phase`, `status`, and `next_action`; ask the user only when the result requests
clarification or approval, then submit the corresponding action. Do not
manually sequence the low-level MCP tools for a normal figure run.

The orchestrator owns the Lifecycle phases Intake, Planning, Execution, Review
and repair, and Export. Each model-assisted phase uses its own Phase prompt and
context. Versioned Phase artifacts, not conversation history, are the handoff
between phases.

## Generation choices

Translate explicit user instructions into `request.generation_intent`, a list of
selections with `unit_id`, `method` (`auto`, `image_model`, `vector`, `hybrid`) and
`scope` (`figure`, `panel`, `module`). Panel/module scopes require `panel_id`;
modules additionally require `members` (existing element/Figure Graph node IDs).
A request to use the image model for "this flowchart" means the entire referenced
flowchart, including labels, arrows and illustrations. Do not split it into SVG
boxes or ask for the same choice again. Disjoint selections can cover different
panels; unspecified content retains automatic routing. Hybrid `ownership` maps
each member to `image_model` or `vector`; the plan resolves it explicitly. Image-owned
top-level labels need `panel_id` and `bbox`, or can be grouped into an image panel/module.

For an entire image-generated flowchart, submit for example:
`"generation_intent": [{"unit_id":"workflow","method":"image_model","scope":"figure","background":"preserve"}]`.
Optional `parameters` and `candidate_count` control that unit; image-model calls
remain subject to the configured Provider capabilities and run budgets. Do not
create SVG artwork for an image-owned unit. Keep semantic nodes/relations as
review requirements. Strict per-object editability can be expressed using
`require_editable_objects`; raster output cannot satisfy that guarantee.

Always show returned `generation_summary` before starting image generation.
If `next_action` is `resume`, continue through `advance_figure_workflow` without
asking for another approval when auto-execution was selected. Otherwise use
existing plan approval. A summary pause is not a completed figure.

If a latest explicit instruction changes the previous method or scope, submit
`action: {"action":"revise_generation_intent","generation_intent":[...],"reason":"the user's instruction"}`.
That instruction already authorizes the revision; do not ask again. An ambiguous
or conflicting target needs only the missing clarification. If a Phase worker
contradicts an already clear choice, correct that output and resume rather than
changing user intent to fit the faulty plan.

For an approved image unit, `apply_repair` accepts `image_edit` or `image_model`
(same-unit regeneration). Never silently substitute SVG, split membership or
remove required text/background. Missing semantic review evidence blocks normal
export; an image's appearance alone is not proof of correctness.

## Non-negotiable production rules

- Intake must resolve output target (`general` or `ppt`), physical width, text
  language, and style before Planning can start.
- Planning must produce a Figure plan, Figure Graph, Solved layout, editable
  blueprint, structure questions, and Generation Conditions before image generation.
  Wait for approval unless the user explicitly selected `auto_execute`.
- Measured data, quantitative plots and their axes remain deterministic.
  A complete non-quantitative image Generation unit may own its descriptive
  labels, symbols and arrows. Outer composition remains local.
- For vector-owned production, `vector_element.content` must contain complete SVG source (`<svg>...</svg>`),
  not a natural-language description. Convert the intended diagram to SVG before
  submitting vector-owned panel elements. Image-owned units need semantic inputs, not new SVG artwork. The runtime renders vector sources locally, saves
  the SVG under `vectors/`, and uses a PNG preview for composition; assembled
  SVG/PDF currently embed that preview rather than editable vector geometry.
  Panel text and equations also use local rendering. These are not image-model calls.
- A missing required asset blocks composition and export, including force export.
  Repair the reported asset IDs before continuing. An empty asset list is not a figure.
- If `next_action` is `review_failed`, inspect the returned error and retained
  validation evidence. Correct the phase worker output before explicitly resuming;
  do not automatically loop retries or treat failed review as export approval.
- Image-generation models produce non-quantitative Generation units: a whole
  figure, named panel, or module can be one asset. Keep its requested background
  and internal text/arrows together. Repairs edit or regenerate that same unit.
- Provider features such as references, masks, structure control, native alpha,
  seeds, and candidate batches must be explicitly declared capabilities;
  unsupported controls fail instead of being silently ignored.
- Deterministic validation findings are authoritative. Export remains blocked
  by blocking findings unless the user explicitly chooses force export and
  provides an audit reason.
- Keep raw CSV/Excel/JSON data local by default and disclose every upload before
  a network operation.
