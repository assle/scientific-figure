---
name: scientific-figure-builder
description: Workflow Skill for the Scientific Figure Builder product. Use it to turn a scientific-figure request into a governed lifecycle, route work to deterministic plots, SVG, and configured image or multimodal providers, validate results, and export publication-ready PNG/SVG/PDF. Not a single-prompt image generator. Works with OpenCode and Codex.
license: MIT
metadata:
  version: "0.3.2"
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

## Non-negotiable production rules

- Intake must resolve output target (`general` or `ppt`), physical width, text
  language, and style before Planning can start.
- Planning must produce a Figure plan, Figure Graph, Solved layout, editable
  blueprint, structure questions, and Generation Conditions before paid work.
  Wait for approval unless the user explicitly selected `auto_execute`.
- Data plots, axes, exact numbers, equations, labels, and final composition
  come from deterministic Python/SVG/local assembly.
- `vector_element.content` must contain complete SVG source (`<svg>...</svg>`),
  not a natural-language description. Convert the intended diagram to SVG before
  submitting structured panel elements. The runtime renders it locally, saves
  the SVG under `vectors/`, and uses a PNG preview for composition; assembled
  SVG/PDF currently embed that preview rather than editable vector geometry.
  Panel text and equations also use local rendering. These are not image-model calls.
- A missing required asset blocks composition and export, including force export.
  Repair the reported asset IDs before continuing. An empty asset list is not a figure.
- If `next_action` is `review_failed`, inspect the returned error and retained
  validation evidence. Correct the phase worker output before explicitly resuming;
  do not automatically loop retries or treat failed review as export approval.
- Image-generation models produce only isolated, non-quantitative raster
  assets; image editing is allowed only for eligible raster repairs.
- Provider features such as references, masks, structure control, native alpha,
  seeds, and candidate batches must be explicitly declared capabilities;
  unsupported controls fail instead of being silently ignored.
- Deterministic validation findings are authoritative. Export remains blocked
  by blocking findings unless the user explicitly chooses force export and
  provides an audit reason.
- Keep raw CSV/Excel/JSON data local by default and disclose every upload before
  a network operation.
