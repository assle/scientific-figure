---
name: scientific-figure-builder
description: Orchestrate publication scientific figures. Understand a figure request, decompose it into rendering tasks, route each to the right engine (Python plots, SVG, Volcengine Ark image/vision models), validate results, and assemble final PNG/SVG/PDF. Not a single-prompt image generator. Works with OpenCode and Codex; core modules are platform-independent.
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
3. Call `check_figure_requirements` and ask the user every unresolved required
   question one at a time: output target (`general` vs `ppt`), figure width
   (half-column 6.5 cm vs full-column 14 cm), figure text language (`zh` vs
   `en`), and figure style (`default` vs a custom style reference). If the
   user does not specify, use the default, but still ask first. Do not proceed
   until every question is resolved.
4. Classify task: `data_plot`, `schematic`, `hybrid`, or `figure_decomposition`.
5. Analyze reference images with the configured Ark vision model (if any).
6. Create a versioned figure plan + no-cost SVG layout wireframe.
7. Show plan, upload list, model-call estimate, and wireframe. **Wait for
   approval before any paid generation.**
8. If >=3 AI assets, generate one style-anchor asset and pause for approval.
9. Generate isolated assets; render plots and precise geometry locally.
10. Deterministic + multimodal validation; retry quality failures at most twice.
11. Assemble the figure automatically; validate the complete figure.
12. Export PNG/SVG/PDF (optional PPTX); write asset manifest, validation report,
    and generation report into a versioned run directory.

`auto_execute: true` is an explicit opt-in. Default = plan approval then execute.
Required clarifications are always asked first, even with `auto_execute: true`.
Before writing any script, rendering any plot, generating any asset,
assembling, or exporting, resolve every requirement above with the user.

## Configuration

Three layers merged in order: Skill defaults < user-local private config <
project config < per-run overrides. The Ark API key is read from `ARK_API_KEY`
or a user-private file and is **never** written to the repo, reports, prompts,
or run manifests. Model roles (`image_generate`, `image_edit`, `vision_analyze`,
`vision_validate`) are configured independently with fixed IDs. No `latest`
resolution or silent upgrades. See `references/workflow-details.md`.

## Tools

Capability-oriented MCP tools (plan section 8): `initialize_figure_project`,
`analyze_reference_figure`, `check_figure_requirements`, `create_figure_plan`,
`create_layout_wireframe`, `generate_image_asset`, `edit_image_asset`,
`render_scientific_plot`, `render_vector_element`, `validate_image_asset`,
`validate_plot_data`, `assemble_figure`, `validate_assembled_figure`,
`export_figure`, `resume_figure_run`. Ark model names are never exposed in
these instructions.

## Validation

Two layers, in priority order **source geometry > pixel rules > OCR > VLM**:

- **Deterministic geometry**: formal text, axes, ticks, legends, colorbars and
  panel labels are located from real source-object bounding boxes
  (`layout_manifest.json`), not by guessing. Overlap, clipping, panel-label
  consistency, typography and colorbar collisions are checked deterministically.
- **Local VLM review**: only enlarged crops of *suspect* regions are sent to the
  vision model. It enriches (confidence, repair hint) but **never downgrades a
  geometry-confirmed error to a pass**.
- **OCR fallback**: optional (PaddleOCR), only for raster/AI assets without
  layout metadata — never for Python data-plot numerics.

The vision model never judges numerical accuracy from pixels; that stays with
`validate_plot_data`. Blocking errors halt export; warnings do not.

## References (load on demand)

- `references/routing-rules.md` - full element-to-engine routing table.
- `references/workflow-details.md` - configuration, approval, budget, resume.
- `references/ark-interfaces.md` - Ark auth, request schema, rate limits.
- `references/output-contract.md` - run directory layout and output formats.
- `references/optics-materials-templates.md` - domain templates.
