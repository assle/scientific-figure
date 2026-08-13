---
description: Orchestrate a scientific figure (init, plan, run, resume, validate, export)
---
You are invoking the scientific-figure-builder skill.

Load the `scientific-figure-builder` skill, then perform the requested
subcommand from `$ARGUMENTS`:

- `init` - initialize project configuration (`.scientific-figure/`) with no
  secrets. Read the Ark API key from `ARK_API_KEY`; never write it anywhere.
- `plan` - inspect the request and local inputs, **ask for the output target if
  it is not already stated** (`general` for PNG/SVG/PDF vs `ppt` for an editable
  PowerPoint-friendly figure, and whether PPTX is needed), **also ask for the
  figure width if not stated** (half-column 6.5 cm or full-column 14 cm), then
  classify the task, analyze reference images (if any), create a versioned
  figure plan and a no-cost SVG layout wireframe. Show the plan, upload list,
  model-call estimate, and wireframe. **Wait for approval before any paid
  generation.** Keep raw data local by default.
- `run` - execute the approved plan: generate isolated transparent assets via
  the Ark image model, render data plots and precise geometry locally with
  Python/SVG, validate, and assemble. If there are three or more AI assets,
  generate one style-anchor asset first and pause for approval. Retry quality
  failures at most twice per asset.
- `resume` - resume an interrupted run from its run directory without
  repeating completed work; invalidate only affected downstream artifacts.
- `validate` - run deterministic and multimodal validation; classify results as
  `error` (blocks export) or `warning` (allows export but is recorded).
- `export` - export final PNG, SVG, and PDF (optional PPTX) and write the asset
  manifest, validation report, and generation report into the versioned run
  directory.

Routing rules (do not deviate): data plots, axes, exact numbers, equations, and
periodic arrays come from Python/SVG only; the Ark image model produces only
isolated, non-quantitative visual assets; final compound figures are assembled
by Python, never by the image model. If the request is scientifically ambiguous,
pause and ask the user before proceeding. If the output target
(`general` vs `ppt`) is not specified, ask for it before creating the plan. If
the figure width is not specified, ask whether the user needs half-column
6.5 cm or full-column 14 cm.
