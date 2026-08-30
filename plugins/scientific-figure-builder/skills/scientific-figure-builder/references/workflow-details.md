# Workflow details

Configuration, approval, budget, and resume behavior (plan sections 5 and 12).

## Lifecycle orchestration

The single Orchestrator owns the run lifecycle: Intake, Planning, Execution,
Review and repair, and Export. Calling Agent commands are adapters to this
seam; they do not sequence low-level MCP tools independently.

Intake produces a versioned Figure brief. Planning consumes only a completed
brief and produces a Figure plan plus wireframe. Execution consumes only an
approved plan and uses Python, SVG, image generation/editing, and assembly as
Generation routes. Review produces a Validation report or targeted Repair
plan. Export is deterministic and crosses the Export gate.

The Figure Planning Module also derives a Figure Graph, Solved layout, editable
SVG blueprint, graph-derived structure questions, and schema-governed
Generation Conditions before approval. Each Generation Condition
combines scientific intent, Style Bible, Publication profile, Reference roles,
Provider capabilities, and cache identity. Asset bounding boxes are relative to
their panel when explicitly declared; layout-only revisions preserve raster
assets. After a Style anchor is approved, Execution derives a separate
anchor-conditioned Execution artifact without rewriting the approved Planning
conditions.

Final validation compares the authoritative Figure-plan label and equation map
with the source-aware assembly manifest using exact text checks. The offline
regression set includes twenty single-axis mechanism-figure defects spanning
structure, text, geometry, phase organization, publication constraints, and
raster editing.

Each model-assisted lifecycle phase receives a fresh Phase worker context with
only its Phase prompt, allowed tools, and upstream Phase artifacts. Prompt
version, prompt hash, and allowed tools are recorded under the run's
`prompts/` directory. Workers return schema-valid artifacts but do not mutate
Run state or write arbitrary downstream outputs.

## Configuration layers (merged in order)

1. Skill defaults (safe rendering defaults, templates, schema versions, limits).
2. User-local private configuration (provider references, fixed model/Endpoint IDs).
3. Project configuration (`.scientific-figure/project.yaml`, `style_bible.json`).
4. Per-run overrides.

## Secrets

Provider credentials prefer the system credential store entry referenced by a
stable `credential_id`, then fall back to the configured environment variable.
Never write them to a repository, report, prompt log, or run manifest. Project
and global config must contain no secret values. Use `python -m figure_tools
gui` to edit global model/provider routes; the native window writes only YAML
metadata and keeps credential values in the system store.

## Model roles

The canonical online roles use fixed IDs:

```yaml
models:
  phase_reasoning: { model: "<optional-fixed-model-or-endpoint-id>" }
  image_generate: { model: "<fixed-model-or-endpoint-id>", provider: openai }
  vision_analyze: { model: "<fixed-model-or-endpoint-id>" }
  vision_validate: { model: "<fixed-model-or-endpoint-id>" }
```

`phase_reasoning` is optional. When absent, the schema-equivalent offline Phase
worker handles Intake, Planning, and Review and repair.

`image_edit` is an optional override for generated or source-less raster assets.
When it is absent, reference-image revision reuses `image_generate`. Scientific
plots and vector elements are changed at their source and rendered again.

No `latest` resolution or silent model upgrades.

## Style precedence

Explicit user instruction > supplied style-reference image > project
`style_bible.json` > Skill defaults.

Publication profiles are independent of this precedence: they own physical
dimensions, final typography, accessibility, vector editability, and export
constraints rather than visual tone. `nature_research` is available alongside
the general profile.

## Approval

- Default: create plan + wireframe, show plan/upload-list/estimate, wait for
  approval before any paid generation.
- `auto_execute: true` is an explicit opt-in.
- If a task has >=3 AI assets, generate one style-anchor asset and pause for
  approval before continuing.
- Require fresh approval before exceeding the configured paid-call budget.
- Required clarifications are a hard gate before any rendering, generation,
  assembly, or export. They are always asked first, even with
  `auto_execute: true`.

## Output target clarification

The output target is required before a plan is created or any paid generation
begins. If the user has not explicitly selected one, ask:

- `general`: portable scientific figure exports (PNG, SVG, PDF); SVG text is
  normalized as paths for broad compatibility.
- `ppt`: PowerPoint-friendly output; SVG text remains editable and is
  normalized for Office import. Usually combined with optional PPTX export.

Record the answer in the structured request as `export_target` and, when the
user asks for an editable deck, `include_pptx: true`. Do not default silently.

## Figure width clarification

The figure width is also required before a plan is created or paid generation
begins. If the user has not explicitly selected one, ask:

- Half-column: 6.5 cm.
- Full-column: 14 cm.

Record the answer as `figure_width_cm`. Derive the canvas height from the
default canvas aspect ratio unless the user supplies a custom height.

## Language clarification

The figure text language is required before a plan is created. If the user has
not explicitly selected one, ask:

- Chinese (`zh`).
- English (`en`).

Record the answer as `language`. Do not silently infer it from the input data.

## Style clarification

The figure style is required before a plan is created. If the user has not
explicitly selected one, ask whether to use the default publication style or a
custom style reference. Record the answer as `style`; the default is
`"default"`, which resolves to `style_bible.json` / `publication.mplstyle`.

## Default paid-call budget

- 1 reference-analysis call.
- 1 initial generation call per asset.
- Up to 2 quality retries per asset.
- 1 final semantic validation call per asset.
- 1 final assembled-figure validation call.

## Reliability

- Max quality retries per asset: 2.
- Transient network/rate-limit retries are tracked separately from quality retries.
- Default independent-asset concurrency: 2.
- Exponential backoff for provider rate limits.
- Cache key from model ID + prompt + parameters + reference hashes; reuse exact
  cache hits unless forced regeneration is requested.
- Persist step outputs and hashes for resume; regenerate only invalidated
  downstream steps; new version for every user-visible revision.

## Privacy

- Keep raw CSV/Excel/JSON data local by default.
- Upload only explicitly listed reference images.
- Never upload an entire project directory.
- List all files that will be uploaded before approval.
