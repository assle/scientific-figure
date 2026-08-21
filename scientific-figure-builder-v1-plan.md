# Scientific Figure Builder v1 Implementation Plan

## Document status

- Status: approved implementation baseline
- Target platform: OpenCode first
- Skill name: `scientific-figure-builder`
- Execution provider: Volcengine Ark only
- This document is an implementation plan. Do not expand v1 scope without explicit approval.

## 1. Objective

Build an OpenCode-first scientific-figure orchestration Skill. The Skill must
understand a figure request, decompose it into appropriate rendering tasks,
route each task to the correct engine, validate the results, and assemble the
final figure.

This is not a single-prompt image-generation Skill.

The core schemas, Python modules, and MCP interfaces must remain independent of
OpenCode so another agent platform can reuse them later.

## 2. Hard responsibility boundaries

| Component | Responsibilities | Prohibited work |
|---|---|---|
| OpenCode planning model | Understand requests, classify tasks, create plans, select tools, summarize validation | Invent scientific data or directly produce final raster figures |
| Ark multimodal analysis model | Analyze reference figures, identify panels and objects, extract text candidates, report uncertainty | Decide whether numerical source data are correct |
| Ark multimodal validation model | Check semantic structure, object count, perspective, style consistency, unwanted text, and final layout | Validate quantitative accuracy from pixels |
| Ark image-generation model | Generate or edit isolated, complex, non-quantitative visual assets | Generate data plots, axes, tick labels, exact numbers, equations, periodic arrays, or final compound figures |
| Python | Quantitative plots, precise geometry, file validation, composition, export, effective-DPI checks | Invent missing experimental values |
| SVG | Arrows, connectors, labels, equations, regular geometry, simple diagrams | Produce complex photorealistic equipment |
| PPTX | Optional editable text, shapes, and final slide composition | Serve as the scientific computation engine |

Examples:

- Semi-realistic optical-fiber body: Ark image model.
- Exact periodic grating: Python or SVG.
- Beam and arrow: SVG.
- Coupling-efficiency curve: Python.
- Labels, angles, and equations: SVG or PPTX.
- Reference-figure decomposition: Ark multimodal analysis model.
- Final assembly: Python and SVG.

## 3. v1 scope

### Included inputs

- Natural-language figure requests.
- One or more reference figures.
- CSV, Excel, or JSON data files.
- Optional style-reference images.

### Included outputs

- Versioned figure plan.
- Layout wireframe for approval.
- Independent transparent schematic assets.
- Reproducible Python data plots and the exact data used.
- SVG elements for arrows, labels, equations, and regular geometry.
- Automatically assembled final PNG, SVG, and PDF.
- Optional editable PPTX.
- Asset manifest, validation report, and generation report.

### Explicit exclusions

- Blender.
- Animation.
- Interactive web visualizations.
- Rotatable 3D models.
- Providers other than Volcengine Ark.
- Automatic full-paper PDF interpretation.
- Direct one-shot generation of a formal compound scientific figure.
- Accessibility checks such as color-blindness simulation.

Retain ordinary publication-legibility checks: font size, line width, panel
label consistency, legend obstruction, cropping, and effective resolution.

## 4. Primary user workflow

1. Initialize the project configuration on first use.
2. Inspect the request and local inputs.
3. Keep raw experimental data local by default.
4. Upload only explicitly listed reference images required by Ark.
5. Classify the task as `data_plot`, `schematic`, `hybrid`, or
   `figure_decomposition`.
6. Analyze reference images with the configured Ark multimodal analysis model.
7. Create versioned structured plans and a no-cost SVG layout wireframe.
8. Show the plan, upload list, model-call estimate, and wireframe to the user.
9. Wait for approval before any paid generation.
10. If the task has three or more AI assets, generate one style-anchor asset and
    pause for approval.
11. Generate or edit isolated assets.
12. Render data plots and precise geometry locally.
13. Perform deterministic and multimodal validation.
14. Retry quality failures at most twice per asset.
15. Assemble the complete figure automatically.
16. Validate the complete figure.
17. Export final formats and write reports.
18. Preserve all inputs, plans, parameters, prompts, hashes, and outputs in a
    versioned run directory.

Provide `auto_execute: true` as an explicit opt-in. The default remains
plan approval followed by execution.

## 5. Configuration model

Use three configuration layers, merged in this order:

```text
Skill defaults
  < user-local private configuration
  < project configuration
  < per-run overrides
```

### Skill defaults

Contain safe rendering defaults, generic templates, schema versions, and
default limits.

### User-local private configuration

Contain:

- Ark API key reference.
- Fixed Ark model IDs or Endpoint IDs.
- Optional private endpoint settings.

Read the API key from an environment variable such as `ARK_API_KEY` or a
user-private file. Never write it to a repository, report, prompt log, or run
manifest. Provide only an example private configuration.

### Project configuration

Create automatically on first use:

```text
.scientific-figure/
├── project.yaml
├── style_bible.json
└── .gitignore
```

The project configuration may contain publication dimensions, palette, fonts,
style overrides, export formats, concurrency, call budgets, and domain-template
selection. It must contain no secrets.

### Required model roles

Configure roles independently, even if two roles initially use the same model:

```yaml
models:
  image_generate:
    model: "<fixed-model-or-endpoint-id>"
  image_edit:
    model: "<fixed-model-or-endpoint-id>"
  vision_analyze:
    model: "<fixed-model-or-endpoint-id>"
  vision_validate:
    model: "<fixed-model-or-endpoint-id>"
```

Do not implement `latest` model resolution or silent model upgrades.

## 6. Proposed package layout

Distribute the Skill, MCP server, schemas, templates, tests, and installer as one
package while keeping internal modules separate:

```text
scientific-figure-builder/
├── SKILL.md
├── schemas/
│   ├── figure-plan.schema.json
│   ├── plot-spec.schema.json
│   ├── asset-manifest.schema.json
│   ├── style-bible.schema.json
│   ├── run-state.schema.json
│   └── validation-report.schema.json
├── references/
│   ├── routing-rules.md
│   ├── workflow-details.md
│   ├── provider-interfaces.md
│   ├── output-contract.md
│   └── optics-materials-templates.md
├── templates/
│   ├── default-project.yaml
│   ├── default-style-bible.json
│   ├── publication.mplstyle
│   └── plot-recipes/
├── figure_tools/
│   ├── server.py
│   ├── config.py
│   ├── state.py
│   ├── ark/
│   ├── planning/
│   ├── plotting/
│   ├── vector/
│   ├── imaging/
│   ├── validation/
│   ├── assembly/
│   └── export/
├── install/
│   ├── configure_opencode.py
│   └── config-snippets/
├── commands/
│   └── scientific-figure.md
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── pyproject.toml
```

Keep `SKILL.md` concise. Put detailed schemas, API notes, and domain recipes in
one-level-deep references and load them only when required.

## 7. Versioned core schemas

Every core document must include:

```json
{
  "schema_version": "1.0"
}
```

Implement migration support before introducing a breaking schema version.

### `figure_plan.json`

Minimum content:

- Figure and run IDs.
- Canvas aspect ratio and physical dimensions.
- Units.
- Panels.
- Normalized bounding boxes `[x, y, width, height]`.
- Physical sizes.
- Asset IDs, types, z-order, and dependencies.
- Routing decision for every element.
- Style-bible reference.
- Text and equation elements.
- Assumptions, uncertainties, and user-input requirements.
- Estimated paid model calls.
- Planned uploads.
- Approval status.

### `plot_spec.json`

Minimum content:

- Chart type and recipe version.
- Source-data path and content hash.
- Column mapping and units.
- Series, errors, transformations, and filters.
- Axes, scales, ticks, legends, and labels.
- Figure dimensions and style.
- Export formats and DPI.
- Validation expectations.

Users should not need to write this JSON manually. The planning layer creates
it, and a fixed renderer consumes it. Generate a new tested plot recipe only
when the existing recipes cannot express the requested plot.

### `asset_manifest.json`

Minimum content:

- Asset ID and type.
- Source or generated file path.
- Content hash.
- Generating model and parameters where applicable.
- Prompt and reference-image hashes.
- Pixel dimensions and transparency status.
- Placement, z-order, and style-anchor relationship.
- Validation result.
- Parent asset for edited versions.

### `style_bible.json`

Minimum content:

- Palette.
- View and projection.
- Lighting and material language.
- Stroke widths.
- Font family, sizes, and equation style.
- Background and shadow policy.
- Forbidden elements.
- Style-reference hashes.

Style precedence:

```text
Explicit user instruction
  > supplied style-reference image
  > project style_bible.json
  > Skill defaults
```

### `run_state.json`

Minimum content:

- Run ID and parent run ID.
- Current step.
- Step status and output hashes.
- Call counts and budget.
- Retry counters separated by transient and quality failures.
- Cache hits.
- Approval checkpoints.
- Resume information.

## 8. MCP tool contract

Expose stable capability-oriented tools. Do not expose Ark-specific model names
in Skill instructions.

### Required tools

```text
initialize_figure_project
analyze_reference_figure
create_figure_plan
create_layout_wireframe
generate_image_asset
edit_image_asset
render_scientific_plot
render_vector_element
validate_image_asset
validate_plot_data
assemble_figure
validate_assembled_figure
export_figure
resume_figure_run
```

### Key behavioral requirements

- `analyze_reference_figure` calls the configured Ark analysis model and
  returns structured panels, objects, text candidates, confidence values, and
  uncertainties.
- `generate_image_asset` and `edit_image_asset` produce one isolated object by
  default.
- `validate_image_asset` combines deterministic checks with the configured Ark
  validation model.
- `validate_plot_data` compares rendered inputs against source data
  deterministically and never relies on visual judgment for numerical accuracy.
- `assemble_figure` uses the approved plan and never asks the image model to
  generate the final compound figure.
- Every paid call checks and updates the run budget.
- Every tool operation is idempotent when given identical inputs, unless the
  caller explicitly requests forced regeneration.

## 9. Image-asset rules

Every formal AI-generated asset must:

- Contain one isolated object unless its specification explicitly defines a
  tightly coupled object group.
- Have generous margins.
- Contain no text, equations, labels, arrows, frame, watermark, or scene
  background.
- Match the approved style bible and style anchor.
- Use a real alpha channel for transparency.
- Preserve semi-transparent scientific elements such as glass and beams.

Transparency workflow:

```text
Request transparent output
→ inspect the alpha channel
→ perform background removal if needed
→ validate edges and subject completeness
→ stop for human review if transparent or glass elements are damaged
```

For insufficient effective resolution:

1. Regenerate at higher resolution.
2. Use reference-preserving image editing or restoration.
3. Use ordinary interpolation only as a last resort.

Do not claim that interpolation creates new scientific detail.

Default candidate count is one. Allow a per-asset override. If multiple
candidates exist, let the multimodal model rank them, but require user selection
when candidates differ scientifically.

## 10. Data, vector, and composition rules

### Data plots

- Keep raw CSV, Excel, and JSON data local by default.
- Preserve the exact plotted data as `data_used.csv`.
- Use fixed recipe-driven rendering.
- Export plot source, spec, SVG, PDF, and PNG.
- Never infer missing units, error definitions, or scientific values.

### Regular structures

Use Python or SVG for:

- Periodic gratings and arrays.
- Scales and ticks.
- Neural-network nodes.
- Repeated geometry.
- Exact angles and dimensions.

Permit image generation only through an explicit `visual_priority` override for
non-quantitative drafts.

### Text and equations

- Render ordinary labels as SVG or editable PPTX text.
- Render equations from LaTeX to SVG.
- Extract text from references into structured `text_elements`.
- Require confirmation for uncertain OCR or equation recognition.

### Composition

Automatically produce the formal assembled figure. Preserve every source
element independently for later editing.

## 11. Validation policy

### Deterministic image checks

- File integrity and format.
- Dimensions.
- Alpha channel.
- Edge clipping and margins.
- Effective DPI at final physical size.
- Unexpected blank output.

### Multimodal semantic checks

- Correct object count.
- Required structure present.
- Perspective and orientation.
- Forbidden text or unrelated objects.
- Style-bible consistency.
- Reference fidelity where applicable.

### Plot checks

- Source-data hash.
- Columns and units.
- Sample counts.
- Missing-value handling.
- Transformations.
- Error-bar definitions.
- Rendered series inputs.

### Final-figure checks

- Panel and element placement.
- Z-order.
- Missing assets.
- Labels and equations.
- Font sizes and line widths.
- Panel label consistency.
- Legend obstruction.
- Cropping and effective resolution.

Do not implement color-blindness or other accessibility checks in v1.

Classify validation results:

- `error`: block formal export.
- `warning`: allow export but record it in the report.

Scientific errors cannot be automatically waived.

## 12. Reliability, cost, and privacy

- Maximum quality retries per asset: two.
- Treat transient network or rate-limit retries separately from quality retries.
- Default independent-asset concurrency: two.
- Use exponential backoff for Ark rate limits.
- Generate a cache key from model ID, prompt, parameters, and reference hashes.
- Reuse exact cache hits unless forced regeneration is requested.
- Persist step outputs and hashes for resume.
- Regenerate only invalidated downstream steps.
- Create a new version for every user-visible revision.
- Record model ID, Endpoint ID, prompt, reference hashes, dimensions, seed when
  available, parameters, and timestamp.
- Do not promise pixel-identical reproduction for AI images.
- Require exact reproducibility for Python and SVG results.
- List all files that will be uploaded before approval.
- Never upload an entire project directory.
- Keep original experimental data local unless the user explicitly authorizes
  upload.

Default paid-call budget:

- One reference-analysis call.
- One initial generation call per asset.
- Up to two quality retries per asset.
- One final semantic validation call per asset.
- One final assembled-figure validation call.

Require fresh approval before exceeding the configured budget.

## 13. Versioned outputs

Use a run directory such as:

```text
runs/2026-07-28_figure-01/
├── inputs/
├── plans/
│   ├── figure_plan.json
│   ├── plot_spec.json
│   └── layout_wireframe.svg
├── prompts/
├── assets/
├── plots/
├── vectors/
├── validation/
├── exports/
│   ├── figure.png
│   ├── figure.svg
│   ├── figure.pdf
│   └── figure.pptx
├── asset_manifest.json
├── style_bible.json
├── run_state.json
└── generation_report.md
```

PPTX is optional. PNG, SVG, and PDF are default formal outputs.

## 14. OpenCode integration

Support natural-language invocation and an explicit command:

```text
/scientific-figure init
/scientific-figure plan
/scientific-figure run
/scientific-figure resume
/scientific-figure validate
/scientific-figure export
```

The installer may prepare the OpenCode MCP configuration, but it must:

1. Inspect existing configuration.
2. Generate a proposed merged configuration.
3. Show the diff.
4. Ask for approval.
5. Back up the original file.
6. Preserve all unrelated providers, MCP servers, and permissions.

Use Python with a `uv`-managed isolated environment. Do not modify the user's
system Python.

## 15. Implementation phases

### Phase 1: Package skeleton and contracts

Deliver:

- Package directory skeleton.
- Concise `SKILL.md`.
- All v1 schemas.
- Default configuration templates.
- Schema validation tests.

Exit criteria:

- Skill metadata and directory naming validate.
- Every example core document validates against its schema.
- No model calls exist yet.

### Phase 2: Deterministic local engines

Deliver:

- Plot-spec loader and validators.
- Initial plot recipes: line, scatter, bar, heatmap, error bar, and multipanel.
- SVG primitives and LaTeX-to-SVG support.
- Wireframe generator.
- Figure compositor.
- PNG, SVG, and PDF exporters.
- Optional PPTX exporter.

Exit criteria:

- A CSV-only example produces reproducible outputs.
- Data-validation tests confirm exact source-to-render mapping.
- Repeated execution produces identical local artifacts.

### Phase 3: Run state and orchestration

Deliver:

- Configuration merging.
- Project initialization.
- Run directory and versioning.
- Approval checkpoints.
- Budget accounting.
- Cache.
- Resume and incremental invalidation.

Exit criteria:

- An interrupted deterministic run resumes without repeating completed work.
- Local edits invalidate only affected downstream artifacts.

### Phase 4: Ark model integration

Deliver:

- Ark authentication and fixed-role model configuration.
- Reference analysis.
- Image generation.
- Reference-image editing.
- Multimodal validation.
- Upload disclosure.
- Rate-limit handling.

Exit criteria:

- Each Ark tool respects the call budget.
- Secrets never appear in logs or artifacts.
- Identical requests produce cache hits.

### Phase 5: Full figure workflow

Deliver:

- Task router.
- Plan and uncertainty handling.
- Style-anchor workflow.
- Independent asset generation.
- Two-layer validation.
- Automatic assembly and final validation.
- Generation report.

Exit criteria:

- Formal outputs never contain image-model-generated text, axes, or data plots.
- Scientific ambiguity pauses for user input.
- Warnings and blocking errors behave as specified.

### Phase 6: Installation and OpenCode command

Deliver:

- OpenCode command definition.
- Safe configuration merger.
- `uv` environment setup.
- Project initializer.

Exit criteria:

- Installation does not overwrite unrelated OpenCode configuration.
- First project use creates valid non-secret project configuration.

### Phase 7: Real-model acceptance testing

Use real paid Ark calls rather than simulated model responses.

Required end-to-end cases:

1. CSV data to a reproducible publication plot.
2. Reference figure to decomposition, transparent assets, and reconstruction.
3. Hybrid multipanel figure containing AI assets, Python plots, and SVG labels.

Evaluate constraints rather than pixel identity:

- API calls succeed.
- Call budgets are respected.
- Outputs have correct formats, dimensions, and alpha channels.
- No forbidden text or unrelated objects appear.
- Quantitative plots match source data.
- Layout matches the approved plan.
- Validation and generation reports are complete.

## 16. Definition of done

v1 is complete only when:

- All schemas are versioned and validated.
- OpenCode can discover and invoke the Skill.
- The MCP server exposes the approved stable tools.
- All four Ark model roles are configured independently with fixed IDs.
- Paid execution requires plan approval by default.
- Raw data remain local by default.
- Data plots are spec-driven and reproducible.
- Generated assets are isolated and genuinely transparent.
- Final PNG, SVG, and PDF are assembled automatically.
- Optional PPTX preserves editable text and shapes.
- Incremental edits, cache, budgets, retries, versioning, and resume work.
- All three real-model acceptance cases pass.
- No excluded v1 feature has been added.

## 17. Authoritative references to verify during implementation

- OpenCode Skills: https://opencode.ai/docs/skills/
- OpenCode Custom Tools: https://opencode.ai/docs/custom-tools/
- OpenCode MCP Servers: https://opencode.ai/docs/mcp-servers/
- Volcengine Ark ImageGenerations API:
  https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01

Ark APIs and available models can change. Before implementing the provider
client, verify the current official Agent Plan documentation, request schema,
authentication requirements, model IDs, image-edit support, output retention,
and rate limits. Keep any updated API details in `references/provider-interfaces.md`,
not in the core Skill workflow.
