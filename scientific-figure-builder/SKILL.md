---
name: scientific-figure-builder
description: Orchestrate publication scientific figures. Understand a figure request, decompose it into rendering tasks, route each to the right engine (Python plots, SVG, configurable image/vision providers), validate results, and assemble final PNG/SVG/PDF. Not a single-prompt image generator. Works with OpenCode and Codex; core modules are platform-independent.
license: MIT
metadata:
  version: "0.1.0"
  provider: configurable
  scope: v1
disable-model-invocation: true
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
- Planning must produce a Figure plan and wireframe and wait for approval before
  paid execution unless the user explicitly selected `auto_execute`.
- Data plots, axes, exact numbers, equations, labels, and final composition
  come from deterministic Python/SVG/local assembly.
- Image-generation models produce only isolated, non-quantitative raster
  assets; image editing is allowed only for eligible raster repairs.
- Deterministic validation findings are authoritative. Export remains blocked
  by blocking findings unless the user explicitly chooses force export and
  provides an audit reason.
- Keep raw CSV/Excel/JSON data local by default and disclose every upload before
  a network operation.

For route-specific details and the run artifact contract, see
`references/routing-rules.md`, `references/workflow-details.md`, and
`references/output-contract.md`.
