---
status: accepted
---

# Deterministic checks are authoritative; VLM only enriches

The merge policy between deterministic validation checks and VLM verdicts is
that **all** deterministic checks (geometry, OCR, asset integrity, resolution)
are protected from VLM downgrade. The VLM may enrich a deterministic check
with additional metadata (repair_action, severity confirmation, detail notes)
but may never change its status from fail to pass.

Previously, only `method == "geometry"` checks were protected; `method == "ocr"`
checks (unexpected_ai_text) could be downgraded to pass by the VLM. This was
narrowed because OCR false positives are better addressed by tuning OCR
confidence thresholds than by allowing a VLM to override a deterministic
finding. The invariant is now simpler: "deterministic checks are authoritative;
the VLM only enriches," with no method-based special-casing.

## Considered options

- **Only geometry protected** (previous behavior): VLM can downgrade OCR
  suspects. Rejected because it makes the merge contract method-dependent and
  fragile, and because VLM judgment is less reliable than tuned OCR thresholds
  for text detection.

- **All deterministic checks protected** (chosen): VLM enriches but never
  downgrades any deterministic finding. Simpler contract, no special-casing.

## Consequences

The `method` field on checks is no longer load-bearing for merge policy. VLM
downgrade logic in `vlm_verify.py` (the `if check.get("method") == "geometry"
return` guard and the subsequent downgrade branch) is removed entirely. OCR
confidence thresholds become the sole mechanism for filtering OCR false
positives before they reach the check list.
