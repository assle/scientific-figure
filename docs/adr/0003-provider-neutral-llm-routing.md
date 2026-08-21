---
status: accepted
---

# Provider-neutral LLM routing by model role

`scientific-figure-builder` no longer treats any single model vendor as a
built-in default. Each model role (`image_generate`, `image_edit`,
`vision_analyze`, `vision_validate`) resolves to a model id plus a named
`provider` that speaks the OpenAI-compatible (`/responses`, `/images/generations`)
or Anthropic-compatible (`/messages`) dialect. There is no hardcoded Ark/Volcengine
SDK transport, no `DEFAULT_PROVIDER_NAME`, and no `ARK_*` env-var coupling; a
vendor such as Ark is now just another provider defined in config.

The reason is per-project/step provider choice. Users wanted to run
understanding/planning, reference analysis, asset generation, and validation
against different vendors (e.g. DeepSeek multimodal for analysis/validation,
Seedream for generation), with `base_url` and credentials configurable per
project rather than fixed to Ark. Routing by role through a `ProviderRouter`
delivers that without code changes per vendor.

## Considered options

- **A: Config-only, keep Ark built-in** — neutralize the default template and
  forward custom `key_env`s, but keep the Ark SDK path and `ark_*` naming.
  Rejected as the first choice only after the user asked for full decoupling;
  it would leave Ark as a special-cased default.
- **B: Full decoupling (chosen)** — remove `RealArkTransport`, rename
  `figure_tools/ark/` → `figure_tools/providers/`, drop `DEFAULT_PROVIDER_NAME`,
  switch model-role env overrides to `SCI_FIG_*`, and make the install scripts
  forward any provider `key_env` from the user config. Ark becomes an ordinary
  config-defined provider.

## Consequences

The provider seam is `figure_tools/providers/`; `test_network_only_via_transport_abstraction`
scopes all network calls there. Model-role keys and the `image_model` routing
label are the stable public vocabulary, while provider names, base URLs, and
`key_env`s are user configuration. The `with_ark` installer flag and the
`volcengine-python-sdk[ark]` optional extra are now obsolete (reduced to
deprecated no-ops / removed). Missing credentials fall back to the deterministic
mock transport instead of failing.
