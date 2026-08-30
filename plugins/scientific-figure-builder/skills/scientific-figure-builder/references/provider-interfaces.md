# Provider interfaces

Provider-neutral integration notes (plan sections 5, 8, 12, 17). The tool is not
wedded to a single vendor: any OpenAI- or Anthropic-compatible endpoint can be
configured per model role.

> Status: **implemented and token-level verified for OpenAI-compatible and
> Anthropic-compatible endpoints.** Network I/O is confined to
> `figure_tools/providers/` via the transport abstraction. There is no built-in
> vendor-specific SDK transport.

## Provider model

A **provider** is a named endpoint described by:

- `type`: `openai` (Responses + Images) or `anthropic` (Messages).
- `base_url`: the API root; the adapter appends the operation path.
- `key_env`: the name of the environment variable holding the credential when
  no Keyring-backed `credential_id` is available.
- optional `credential_id`: a stable UUID locating the credential in the
  operating system credential store.
- optional per-provider flags (`supports_image_edit`,
  `supports_reference_image`, `supports_multi_reference`,
  `supports_mask_edit`, `supports_structure_control`,
  `supports_native_alpha`, `supports_seed`, `supports_candidate_batch`,
  `auth_scheme`, `messages_path`, `anthropic_version`).

Each **model role** is `{model: <id>, provider: <provider-name>}`. The
`ProviderRouter` routes each role to the transport of its referenced provider.
`phase_reasoning` is an optional text-only role: when configured, each
model-assisted Lifecycle phase makes a fresh structured-output call with its
own Phase prompt and context. Without it, the offline Phase worker produces the
same artifact schema.

### Operation routing

| Provider `type` | Phase reasoning | Image generation/editing | Vision (analyze/validate) |
|---|---|---|---|
| `openai` | `POST {base_url}/responses` | `POST {base_url}/images/generations` (`b64_json`) | `POST {base_url}/responses` (`input_image` parts) |
| `anthropic` | `POST {base_url}{messages_path}` | unsupported | `POST {base_url}{messages_path}` (default `/messages`) |

The OpenAI-compatible vision adapter requests structured JSON
(`text.format.type = json_object`) and reads `output_text` (or the
`output[].content[].text` fallback).

## Wiring a DeepSeek multimodal model (Responses API)

DeepSeek's multimodal image-understanding model is accessed through the
OpenAI-compatible Responses API. Verified facts:

- Model: `deepseek-v4-flash-vision-exp`
- Base URL: `https://api.deepseek.com` (`/responses`)
- Images are passed in `input_image` content parts; `image_url` can be a base64
  `data:` URL, an http(s) URL, or a Files API `file_id`. A `detail` field is
  optional. JSON output is supported.

```yaml
models:
  vision_analyze:
    model: deepseek-v4-flash-vision-exp
    provider: deepseek
  vision_validate:
    model: deepseek-v4-flash-vision-exp
    provider: deepseek
providers:
  deepseek:
    type: openai
    base_url: https://api.deepseek.com/
    key_env: DEEPSEEK_API_KEY
```

## Wiring an image-generation model (Seedream or any OpenAI-compatible image API)

Image generation always goes through an `openai` provider using
`/images/generations`. A different model only means a different `base_url` and/or
`model` id. Example with Volcengine Ark Seedream:

```yaml
models:
  image_generate:
    model: <seedream-model-or-endpoint-id>
    provider: ark_seedream
providers:
  ark_seedream:
    type: openai
    base_url: https://ark.cn-beijing.volces.com/api/plan/v3
    key_env: ARK_API_KEY
    supports_image_edit: true
```

Ark (and any vendor) is now just a config-defined provider; it is **not** a
built-in default. For Ark vision, use the `anthropic` dialect
(`auth_scheme: bearer`, `messages_path: /v1/messages`).

## Credentials & security

- Credentials prefer the system credential store entry named by
  `credential_id`, then fall back to the environment variable named by
  `key_env`; the value is never stored in config, artifacts, prompt logs, or
  run manifests.
- The installer forwards the default env vars plus every `key_env` declared in
  the user config, so proxies/agents pass provider keys through to the MCP server.
- `SecretRedactor` strips all configured keys from logged prompts, provider
  errors, MCP errors, and diagnostics.

## Role mapping (internal paid-call role -> config model key)

| Internal role | Config key | Operation |
|---|---|---|
| `phase_reasoning` | optional `phase_reasoning` | isolated Intake, Planning, or Review and repair reasoning |
| `generation` | `image_generate` | isolated asset generation |
| `edits` | optional `image_edit`, else `image_generate` | generated-raster reference revision |
| `reference_analysis` | `vision_analyze` | reference figure analysis |
| `validations` | `vision_validate` | per-asset multimodal validation + local-region review |
| `final_validation` | `vision_validate` | assembled-figure whole-image validation |

## Behaviors

- `analyze_reference_figure` returns structured panels, objects, text
  candidates, confidence, and uncertainties.
- `generate_image_asset` produces one isolated object; `edit_image_asset` is
  reserved for generated or source-less rasters and reuses the generation model
  unless an override is configured. Opaque model output is background-removed to
  a genuinely transparent PNG.
- Execution sends one canonical Generation Condition per raster asset. Content,
  style, structure, parent, and mask references remain distinct through cache,
  provenance, and transport mapping. A required undeclared capability fails
  before the Provider call instead of being ignored.
- Three or more related raster assets use the first approved asset as a style
  anchor for later assets in the same Style group. Candidate generation is
  budgeted explicitly and selects hard-gate-valid results before considering
  softer quality signals.
- `validate_image_asset` combines deterministic image checks with one multimodal
  validation call and returns a `validation-report`-conformant dict.
- Every paid call records against the run budget; identical requests hit the
  content-addressed cache; rate limits use exponential backoff.
- `disclose_uploads(paths)` lists files and hashes before any upload.

## Environment variables

Model-role overrides use `SCI_FIG_*`:

```
SCI_FIG_IMAGE_GENERATE=<image-gen model/Endpoint ID>
SCI_FIG_IMAGE_EDIT=<optional image-edit override>
SCI_FIG_VISION_ANALYZE=<vision model/Endpoint ID>
SCI_FIG_VISION_VALIDATE=<vision model/Endpoint ID>
```

Provider credentials use `key_env` (e.g. `DEEPSEEK_API_KEY`, `ARK_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). `SCIENTIFIC_FIGURE_CONFIG` points at a
non-secret YAML config file.

## Running a real acceptance run

The real-model acceptance tests are config-driven, not vendor-hardcoded: they
build the client exactly like the MCP server (`figure_tools.server._client`), so
model IDs, provider types, `base_url`s, and `key_env`s all come from your config.
No test-code change is needed to point them at any provider.

Steps, from the repo root (no global install needed):

```bash
cd scientific-figure-builder

# 1. Create or select a non-secret XDG config file.
config_file="${XDG_CONFIG_HOME:-$HOME/.config}/scientific-figure-builder/config.yaml"
mkdir -p "${config_file%/*}"
test -f "$config_file" || cp templates/default-project.yaml "$config_file"
export SCIENTIFIC_FIGURE_CONFIG="$config_file"
# 2. Export the credentials referenced by each provider's `key_env`.
export DEEPSEEK_API_KEY="..."      # or whatever your providers use
export ARK_API_KEY="..."

# 3. Run the acceptance tests.
.venv/bin/python -m pytest tests/e2e/test_acceptance_real.py -v
```

These tests call the real providers and incur cost. `test_case1` runs offline
every time; `test_case2` / `test_case3` skip unless a configured provider's
credential is present. The final validation uses `force_export`, because a
non-deterministic vision model may report a blocking summary even for a valid
figure; the report carries the checks either way.

## Cache & billing

Production calls go through a content-addressed cache (`Cache`): identical
requests (same model + prompt + parameters + reference hashes) reuse the cached
result instead of calling the provider again. This is intentional — it avoids
re-paying for identical calls and enables step-level resume. It keyed by model
id and inputs, not by provider, so a cache hit never depends on which provider
served it.

The acceptance tests disable this cache (the client is built with `cache=None`)
so a run reflects fresh provider calls rather than a cached pass. To force a
fresh production-call instead of a cache hit, pass `force=True` on the client
method, or clear the shared cache directory
(`$XDG_CACHE_HOME/scientific-figure-builder/runtime`, defaulting to
`~/.cache/scientific-figure-builder/runtime` on Unix). Set the absolute
`SCIENTIFIC_FIGURE_CACHE_DIR` override when an isolated cache is required.

Credentials are never cached and never written to logs, manifests, or run
directories; the acceptance run asserts no key appears anywhere in the run tree.
