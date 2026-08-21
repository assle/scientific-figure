# Scientific Figure Builder Validation

The validation subsystem that checks assembled scientific figures for layout,
typographic, and semantic issues. It combines deterministic rules with
optional multimodal VLM review.

## Language

**Deterministic check**:
A validation finding produced by a rule-based algorithm (geometry overlap,
OCR text detection, asset integrity, resolution). Deterministic checks are
authoritative; their status can never be downgraded by the VLM.
_Avoid_: hard rule, fixed check, geometric conclusion

**VLM verdict**:
The vision language model's enrichment of a deterministic check. A VLM verdict
provides only a detail description and a repair_action suggestion; it can never
override a deterministic check's status. For whole-figure review, the VLM's
findings are the primary result.
_Avoid_: AI check, model opinion, VLM judgment

**Merge invariant**:
The contract that deterministic check status is immutable post-VLM. The VLM
may add fields (vlm_confirmed, vlm_confidence, repair_action) and notes, but
may not change status from fail to pass on any deterministic check.

**Suspected region**:
A localized area of the composed figure flagged by a deterministic rule as
containing a potential issue. Each suspected region carries a bbox and
element_ids, and may be sent to the VLM for local-region review.
_Avoid_: problem area, defect zone

**Reviewable issue**:
A check_id that is eligible for local-region VLM review. Only issues that have
a deterministic rule producing a fail check with a bbox are reviewable
locally. Issues that originate solely from whole-figure VLM review
(background_residue, legend_obstruction) are not locally reviewable and are
only available when whole-figure review is enabled.
_Avoid_: VLM check, checkable problem

**Local-region review**:
A VLM call that inspects a single enlarged crop of a suspected region. Uses a
short, issue-specific prompt with thinking disabled. Enriches the deterministic
check that produced the suspected region.
_Avoid_: crop check, zoom review

**Whole-figure review**:
A VLM call that inspects the entire composed figure. Catches global issues that
deterministic rules and local crops cannot (style consistency, object count,
cross-panel semantics, background residue). Off by default for latency control.
_Avoid_: final vision check, full-image audit

**Assembled figure**:
The composed figure under final validation, bundled as one object — figure
plan, asset manifest, composed image path, layout manifest, and physical size.
It is the input to `FigureQAEngine`; the engine interface no longer exposes
the assembly details as separate parameters.
_Avoid_: final figure bundle, composed input

**Degraded validation**:
The state when the layout manifest is missing: geometry rules (overlap,
clipping, panel labels, typography, colorbar) cannot run, and the engine emits
an explicit `geometry_checks_skipped` (skipped + warning) finding instead of
faking a pass. Callers can tell from the report exactly which checks did not
run.
_Avoid_: fallback validation, weak check

## Export

**Export gate**:
The decision, shared by the full workflow and the MCP export tool, that
publishes an assembled figure only when the surfaced validation reports allow
it: any report whose summary is blocking refuses export unless `force_export`
explicitly bypasses the gate. The decision lives in the `export_figure` module.
_Avoid_: publish gate, export check

**PPT-ready SVG**:
The `export_target="ppt"` SVG output contract: ordinary text is kept as real
`<text>` elements so PowerPoint can ungroup them into editable text, the font
stack is declared as `Arial, SimSun, sans-serif` (Arial for Latin, 宋体/SimSun
for Chinese), and text without an explicit size defaults to 六号 (7.5 pt) so
font substitution does not re-flow overlapping text.
_Avoid_: ppt export mode, PowerPoint file

## Planning

**Required clarification**:
A mandatory question the user must answer before any rendering, generation,
assembly, or export (output target, figure width, text language, style). The
four questions are defined by the `REQUIRED_CLARIFICATIONS` table;
`create_figure_plan` and `collect_required_clarifications` both derive from
it, so the two output shapes cannot drift.
_Avoid_: pending question, user input requirement

## Model roles & providers

**Multimodal model**:
A model that reads images and understands them (reference-figure analysis,
per-asset validation, and final-figure validation). It never generates images.
Configured under the `vision_analyze` and `vision_validate` roles.
_Avoid_: vision model, image-understanding model

**Image-generation model**:
A model that produces isolated, complex, non-quantitative raster assets. It is
the only role that truly generates pixels; it is configured under the
`image_generate` (and optional `image_edit`) roles. Python/SVG output uses no
model at all.
_Avoid_: drawing model, image model (ambiguous)

**Model role**:
A named slot in the `models:` config keyed by function (`image_generate`,
`image_edit`, `vision_analyze`, `vision_validate`). Each role resolves to one
model id plus a provider reference. The role keys stay stable while the
providers underneath change.
_Avoid_: model, step, flow

**Provider**:
A named endpoint described by `type` (`openai` or `anthropic`), `base_url`,
and `key_env`. The `ProviderRouter` sends each model role to its referenced
provider's transport. No provider is a built-in default; the tool is
vendor-neutral.
_Avoid_: vendor, service, upstream

**Provider type**:
The wire dialect a provider speaks. `openai` covers `/images/generations` and
`/responses`; `anthropic` covers `/messages` (vision only, no image generation).
_Avoid_: protocol, API style

**key_env**:
The name of the environment variable that holds a provider's credential. The
credential is never stored in config, logs, artifacts, or manifests.
_Avoid_: api key, key field
