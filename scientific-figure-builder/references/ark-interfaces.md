# Ark interfaces

Volcengine Ark provider integration notes (plan sections 5, 8, 12, 17).

> Status: **implemented and verified with real paid calls (Phase 7).** The three
> acceptance cases pass against live Ark. Network I/O is confined to
> `figure_tools/ark/` via the transport abstraction.

## Authoritative references

- Volcengine Ark ImageGenerations API:
  https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01

## Verified API facts (Phase 7)

- SDK: `volcenginesdkarkruntime` (install via `volcengine-python-sdk[ark]`).
- Image generation/editing: `client.images.generate(model, prompt, image=,
  response_format='b64_json', output_format='png', size=, seed=, watermark=False)`.
  Response: `resp.data[0].b64_json`. Editing passes the parent image via `image=`
  as a data URL.
- Vision analysis/validation: `client.chat.completions.create(model, messages=[…],
  response_format={'type':'json_object'})` with `image_url` content parts.
- **Plan routing is by base URL + API key** (plan is bound to the key):
  - agent plan (image gen/edit): base URL `https://ark.cn-beijing.volces.com/api/plan/v3`
  - coding plan (vision): base URL `https://ark.cn-beijing.volces.com/api/coding/v3`
- Seedream requires `size` >= 3,686,400 px (1920x1920); default 2048x2048.
- Seedream returns opaque RGB even with `output_format='png'`; genuine
  transparency is achieved by background removal (`figure_tools/imaging/`),
  per the plan section 9 transparency workflow.
- Rate limit: SDK raises `ArkRateLimitError` (429); connection/timeout errors
  (`ArkAPIConnectionError`, `ArkAPITimeoutError`) are also retried as transient.

## Implemented interface

- `figure_tools/ark/auth.py` - reads `ARK_API_KEY` from env or a private file;
  `redact()` strips the key from any text. The key is never serialized.
- `figure_tools/ark/transport.py` - `ArkTransport` interface + `MockArkTransport`.
- `figure_tools/ark/real_transport.py` - `RealArkTransport` (live SDK).
- `figure_tools/ark/client.py` - `ArkClient` with fixed-role model config.

### Role mapping (internal paid-call role -> config model key -> plan)

| Internal role | Config key | Plan | Operation |
|---|---|---|---|
| `generation` | `image_generate` | agent | isolated asset generation |
| `edits` | optional `image_edit`, else `image_generate` | agent | generated-raster reference revision |
| `reference_analysis` | `vision_analyze` | coding | reference figure analysis |
| `validations` | `vision_validate` | coding | per-asset multimodal validation + local-region review |
| `final_validation` | `vision_validate` | coding | assembled-figure whole-image validation |

### Local-region verification (image QA)

`ArkClient.verify_local_region(crop_path, issue_type, context)` sends only the
enlarged evidence crop (plus geometry context) to the vision model under the
`validations` role. The model returns strict JSON:

```json
{
  "confirmed": true,
  "confidence": 0.94,
  "severity": "error",
  "detail": "Panel label overlaps the y-axis title.",
  "move_element_id": "panel_a_label",
  "direction": "right",
  "minimum_shift_px": 12
}
```

Merge policy: a geometry-confirmed error is never downgraded to pass; the VLM
only adds visibility judgment and a repair hint. Empty or failed responses
keep the deterministic result.

### Environment (Phase 7)

```
ARK_API_KEY=<agent-plan API key>
ARK_API_KEY_CODING=<coding-plan API key>
ARK_IMAGE_GENERATE=<image-gen model/Endpoint ID>
ARK_IMAGE_EDIT=<optional image-edit override>
ARK_VISION_ANALYZE=<vision model/Endpoint ID>
ARK_VISION_VALIDATE=<vision model/Endpoint ID>
ARK_AGENT_BASE_URL=<optional image API base URL>
ARK_CODING_BASE_URL=<optional vision API base URL>
```

Model IDs can alternatively be stored without secrets in
`~/.config/scientific-figure-builder/config.yaml` or a project's
`.scientific-figure/project.yaml` under `models`. Precedence is user config,
project config, then `ARK_*` environment variables. `SCIENTIFIC_FIGURE_CONFIG`
can point to another non-secret YAML config file.
Canonical providers are configured with `type: openai | anthropic`, `base_url`,
and a non-secret `key_env` reference. OpenAI-compatible providers handle vision
through `/responses` and image generation through `/images/generations`.
Anthropic-compatible providers handle vision through `/messages` only. Legacy
`protocol: responses` is accepted with migration guidance.
The Volcengine Agent Plan Anthropic dialect explicitly sets `auth_scheme: bearer`
and `messages_path: /v1/messages`; standard Anthropic providers default
to `x-api-key` and `/messages`.
Custom `key_env` values must also be forwarded by the agent's MCP environment
configuration.

### Behaviors

- `analyze_reference_figure` returns structured panels, objects, text
  candidates, confidence, and uncertainties.
- `generate_image_asset` produces one isolated object. `edit_image_asset` is
  reserved for generated or source-less raster assets and reuses the generation
  model unless an override is configured. Opaque model output gets
  background-removed to a genuinely transparent PNG.
- `validate_image_asset` combines deterministic image checks with one multimodal
  validation call and returns a `validation-report`-conformant dict.
- Every paid call records against the run budget; identical requests hit the
  content-addressed cache; rate limits use exponential backoff.
- `disclose_uploads(paths)` lists files and hashes before any upload.
