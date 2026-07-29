---
name: scientific-figure-builder
description: Orchestrate publication scientific figures. Understand a figure request, decompose it into rendering tasks, route each to the right engine (Python plots, SVG, Volcengine Ark image/vision models), validate results, and assemble final PNG/SVG/PDF. Not a single-prompt image generator. OpenCode-first; core modules are platform-independent.
license: MIT
metadata:
  version: "0.1.0"
  provider: volcengine-ark
  scope: v1
---

# Scientific Figure Builder

## What I do

Produce reproducible, publication-quality compound scientific figures from
natural-language requests, reference figures, and CSV/Excel/JSON data. I
decompose a request, route each element to the correct engine, validate the
results, and assemble the final figure.

This is **not** a one-shot image-generation skill. Image models only produce
isolated, non-quantitative visual assets; all data plots, axes, numbers,
equations, and final composition come from deterministic Python/SVG.

## Responsibility boundaries (summary)

- OpenCode planning model: understand, classify, plan, summarize. Never invents
  data or emits final raster figures.
- Ark image model: isolated complex non-quantitative assets only. Never data
  plots, axes, tick labels, exact numbers, equations, or final compound figures.
- Ark vision models: analyze references / validate semantics. Never judge
  numerical accuracy from pixels.
- Python: quantitative plots, precise geometry, composition, export.
- SVG: arrows, connectors, labels, equations, regular geometry.
- PPTX: optional editable text/shapes/composition.

See `references/routing-rules.md` for the full routing table.

## When to use me

Use when the user wants a formal scientific figure: a data plot, a schematic, a
hybrid multipanel figure, or reconstruction of a reference figure. Do not use
for Blender, animation, interactive web viz, rotatable 3D, full-paper PDF
interpretation, or one-shot formal figure generation.

## Workflow (high level)

1. Initialize project config on first use.
2. Inspect request + local inputs; keep raw data local by default.
3. Classify task: `data_plot`, `schematic`, `hybrid`, or `figure_decomposition`.
4. Analyze reference images with the configured Ark vision model (if any).
5. Create a versioned figure plan + no-cost SVG layout wireframe.
6. Show plan, upload list, model-call estimate, and wireframe. **Wait for
   approval before any paid generation.**
7. If >=3 AI assets, generate one style-anchor asset and pause for approval.
8. Generate isolated assets; render plots and precise geometry locally.
9. Deterministic + multimodal validation; retry quality failures at most twice.
10. Assemble the figure automatically; validate the complete figure.
11. Export PNG/SVG/PDF (optional PPTX); write asset manifest, validation report,
    and generation report into a versioned run directory.

`auto_execute: true` is an explicit opt-in. Default = plan approval then execute.

## Configuration

Three layers merged in order: Skill defaults < user-local private config <
project config < per-run overrides. The Ark API key is read from `ARK_API_KEY`
or a user-private file and is **never** written to the repo, reports, prompts,
or run manifests. Model roles (`image_generate`, `image_edit`, `vision_analyze`,
`vision_validate`) are configured independently with fixed IDs. No `latest`
resolution or silent upgrades. See `references/workflow-details.md`.

## Tools

Capability-oriented MCP tools (plan section 8): `initialize_figure_project`,
`analyze_reference_figure`, `create_figure_plan`, `create_layout_wireframe`,
`generate_image_asset`, `edit_image_asset`, `render_scientific_plot`,
`render_vector_element`, `validate_image_asset`, `validate_plot_data`,
`assemble_figure`, `validate_assembled_figure`, `export_figure`,
`resume_figure_run`. Ark model names are never exposed in these instructions.

## References (load on demand)

- `references/routing-rules.md` - full element-to-engine routing table.
- `references/workflow-details.md` - configuration, approval, budget, resume.
- `references/ark-interfaces.md` - Ark auth, request schema, rate limits.
- `references/output-contract.md` - run directory layout and output formats.
- `references/optics-materials-templates.md` - domain templates.
