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
