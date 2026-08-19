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

## Hard rule: interview first

Run a `/grilling` session to collect these four decisions from the user, one
question at a time. Ask the first question, then stop and end your turn. Do not
act until all four are answered:

1. Output target: `general` (PNG/SVG/PDF) or `ppt`? (default `general`)
2. Figure width: half-column 6.5 cm or full-column 14 cm? (default 6.5)
3. Text language: `zh` or `en`? (default `zh`)
4. Style: `default` or custom reference? (default `default`)

If the user does not specify, use the default shown, but still ask first.
`auto_execute` never skips this interview.

## After the interview

Produce reproducible, publication-quality compound scientific figures from
natural-language requests, reference figures, and CSV/Excel/JSON data. Data
plots, axes, exact numbers, equations, and final composition come from
deterministic Python/SVG; configured image models produce only isolated,
non-quantitative visual assets. Never write ad-hoc plotting scripts before the
interview is complete.

Call `check_figure_requirements` when available to confirm the four decisions
are resolved before any rendering, generation, assembly, or export. See
`references/routing-rules.md` for routing and `references/workflow-details.md`
for the full plan/approval/run workflow.
