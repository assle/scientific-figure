# Ark interfaces

Volcengine Ark provider integration notes (plan sections 5, 8, 12, 17).

> Status: **client implemented and unit-tested with a mock transport (Phase 4).**
> No paid calls are made until Phase 7. The transport abstraction
> (`figure_tools/ark/transport.py`) is the single network seam; a real HTTP
> transport is finalized in Phase 7 against verified Ark docs.
>
> Ark APIs and available models can change. Before Phase 7, verify the current
> official documentation, request schema, authentication requirements, model IDs,
> image-edit support, output retention, and rate limits. Keep updated API details
> in this file, not in the core Skill workflow.

## Authoritative references

- Volcengine Ark ImageGenerations API:
  https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01

## Implemented interface (Phase 4)

- `figure_tools/ark/auth.py` - reads `ARK_API_KEY` from env or a private file;
  `redact()` strips the key from any text. The key is never serialized.
- `figure_tools/ark/transport.py` - `ArkTransport` interface + `MockArkTransport`
  (deterministic, no network). Raises `RateLimitError` to exercise backoff.
- `figure_tools/ark/client.py` - `ArkClient` with fixed-role model config.

### Role mapping (internal paid-call role -> config model key)

| Internal role | Config key | Operation |
|---|---|---|
| `generation` | `image_generate` | isolated asset generation |
| `edits` | `image_edit` | reference-image editing |
| `reference_analysis` | `vision_analyze` | reference figure analysis |
| `validations` | `vision_validate` | per-asset multimodal validation |
| `final_validation` | `vision_validate` | assembled-figure validation |

### Behaviors

- `analyze_reference_figure` returns structured panels, objects, text
  candidates, confidence, and uncertainties.
- `generate_image_asset` / `edit_image_asset` produce one isolated object with a
  real alpha channel; metadata records model, parameters, prompt hash, reference
  hashes, pixel dimensions, transparency, and `parent_asset_id` for edits.
- `validate_image_asset` combines deterministic image checks with one multimodal
  validation call and returns a `validation-report`-conformant dict.
- Every paid call records against the run budget (`BudgetExceeded` on breach);
  identical requests hit the content-addressed cache.
- Rate-limit errors trigger exponential backoff with transient retries tracked
  separately from quality retries.
- `disclose_uploads(paths)` lists files and hashes before any upload.
