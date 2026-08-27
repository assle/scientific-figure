# Scientific Figure Builder

Scientific Figure Builder turns a clarified scientific-figure request into reproducible assets, an assembled figure, validation evidence, and exportable outputs. This glossary defines the stable language shared by planning, model routing, configuration, delivery, validation, and export.

## Planning

**Required clarification**:
A question that must be answered before rendering, generation, assembly, or export can begin: output target, figure width, text language, or style.
_Avoid_: pending question, optional preference, user input requirement

## Model routing

**Multimodal model**:
A model that reads images for reference analysis or validation but does not generate image assets.
_Avoid_: vision model, image-understanding model

**Image-generation model**:
A model that produces or revises non-quantitative raster assets; plots, labels, equations, and other reproducible graphics are not image-generation work.
_Avoid_: drawing model, image model

**Model role**:
A stable functional slot for model-assisted work: `image_generate`, optional `image_edit`, `vision_analyze`, or `vision_validate`.
_Avoid_: model, step, flow, agent model

**Model route**:
The binding of one Model role to a Model identifier and a Provider ID.
_Avoid_: model role, Provider, model setting

**Model identifier**:
A Provider-specific identifier accepted for a Model route, such as a model ID, endpoint ID, or gateway alias.
_Avoid_: fixed model list, display name

**Provider**:
A named model endpoint that speaks one supported Provider type; no Provider or vendor is a built-in default.
_Avoid_: vendor, service, upstream, model

**Provider ID**:
The stable configuration identity used by Model routes to reference a Provider; it is distinct from the Provider's vendor or display name.
_Avoid_: Provider name, vendor name, credential ID

**Provider type**:
The wire dialect a Provider speaks: OpenAI Compatible or Anthropic Compatible.
_Avoid_: vendor, SDK, model family

**Provider capability**:
An explicitly declared optional behavior of a Provider, such as reference-image editing, beyond the guarantees of its Provider type.
_Avoid_: Provider type, assumed support, model feature

**Image-edit inheritance**:
The state in which the optional `image_edit` Model route is absent and editing reuses the `image_generate` Model route.
_Avoid_: edit fallback, duplicate route, automatic capability

**Route compatibility**:
Whether a Model route's Provider type and declared Provider capabilities can fulfil its Model role.
_Avoid_: connection status, Provider health, model availability

## Configuration and credentials

**Global configuration**:
User-scoped defaults for Model routes and Providers that apply across projects and may be managed by the Configuration app.
_Avoid_: user config, default project, Agent configuration

**Project configuration**:
Project-scoped settings that override Global configuration for one scientific-figure project and are not managed by the Configuration app.
_Avoid_: global config, machine config, GUI config

**Effective configuration**:
The resolved configuration used for a run after defaults, Global configuration, Project configuration, and explicit run-time overrides have been combined.
_Avoid_: saved config, GUI state, source file

**Configuration draft**:
An editable, unsaved representation of Global configuration used by the Configuration app until the user saves or discards it.
_Avoid_: effective configuration, GUI state, temporary config

**Configuration conflict**:
An external change to Global configuration made after a Configuration draft was opened, requiring the draft to be reloaded before it can be saved.
_Avoid_: validation error, merge conflict, save failure

**Provider credential**:
The secret used to authenticate a Provider; it is never part of configuration, logs, artifacts, manifests, or error details.
_Avoid_: Provider ID, credential reference, secret field

**Credential reference**:
Non-secret configuration metadata that locates a Provider credential without containing the credential itself.
_Avoid_: API Key, secret, password

**`credential_id`**:
A stable, non-secret Credential reference that identifies one Keyring-backed credential and remains unchanged when its Provider ID is renamed.
_Avoid_: Provider ID, API Key, Keyring password

**`key_env`**:
A non-secret Credential reference naming the environment variable that supplies an Environment-backed credential.
_Avoid_: API Key, environment value, secret field

**Keyring-backed credential**:
A Provider credential stored in the operating system's System credential store and located by `credential_id`.
_Avoid_: keyring file, YAML secret, encrypted config

**Environment-backed credential**:
A Provider credential supplied by the environment variable named by `key_env` or by the Provider's established environment convention.
_Avoid_: Keyring-backed credential, config secret, environment name

**Temporary credential**:
A Provider credential supplied only to a Connection test and discarded without becoming a Credential reference or Keyring-backed credential.
_Avoid_: draft credential, unsaved API Key, Environment-backed credential

**System credential store**:
The operating-system facility that protects Keyring-backed credentials for the current user.
_Avoid_: secrets file, YAML store, application database

**Credential resolution**:
The selection of a Provider credential from its configured sources, preferring an available Keyring-backed credential and otherwise checking the Environment-backed credential.
_Avoid_: credential migration, Provider routing, silent plaintext fallback

**Credential status**:
A non-secret summary of whether a Provider credential is configured and which source supplies it, without exposing the full credential.
_Avoid_: API Key value, credential preview, connection status

**Credential replacement**:
Changing the Provider credential located by an existing `credential_id` while keeping that Credential reference stable.
_Avoid_: credential creation, Provider rename, key migration

**Credential removal**:
Retiring a Keyring-backed credential and its `credential_id` while leaving any `key_env` Environment-backed credential reference unchanged.
_Avoid_: Provider deletion, credential replacement, environment cleanup

**Configuration app**:
The native desktop interface for managing Global configuration, Model routes, Providers, and Keyring-backed credentials; it does not configure the Calling Agent or run figure-building tasks.
_Avoid_: task console, project editor, Agent settings, web dashboard

**Connection test**:
A user-initiated, minimal Provider invocation that checks the current Configuration draft, optionally with a Temporary credential, and may incur Provider cost.
_Avoid_: health check, automatic probe, benchmark, task run

**Calling Agent**:
The Agent that invokes Scientific Figure Builder and remains responsible for the surrounding conversation and workflow.
_Avoid_: configured Agent, main model role, Scientific Figure Builder Agent

## Delivery

**Global installation**:
A user-scoped delivery of the Configuration app and Calling Agent integrations that can be used across projects.
_Avoid_: Global configuration, system installation, project setup

**Project installation**:
A delivery of Calling Agent integrations for one project that does not own the Global configuration or global Configuration app launcher.
_Avoid_: Project configuration, local environment, per-run setup

## Validation

**Deterministic check**:
A rule-based validation finding whose status is authoritative and cannot be downgraded by a VLM verdict.
_Avoid_: hard rule, fixed check, geometric conclusion

**VLM verdict**:
A multimodal model's enrichment of a Deterministic check, or the primary finding of Whole-figure review.
_Avoid_: AI check, model opinion, VLM judgment

**Merge invariant**:
The rule that a VLM verdict may enrich a Deterministic check but may never change its status from fail to pass.

**Suspected region**:
A localized area of an Assembled figure identified by a Deterministic check as containing a possible issue.
_Avoid_: problem area, defect zone

**Reviewable issue**:
A failed Deterministic check with localized evidence that is eligible for Local-region review.
_Avoid_: VLM check, checkable problem

**Local-region review**:
A VLM review of one enlarged Suspected region that enriches the Deterministic check which identified it.
_Avoid_: crop check, zoom review

**Whole-figure review**:
A VLM review of the complete Assembled figure for global visual or semantic issues that local evidence cannot establish.
_Avoid_: final vision check, full-image audit

**Assembled figure**:
The composed scientific figure together with the plans, manifests, dimensions, and placements needed to validate it as one subject.
_Avoid_: final figure bundle, composed input

**Degraded validation**:
Validation that explicitly reports which geometry checks were skipped because the evidence required to run them is unavailable.
_Avoid_: fallback validation, weak check, assumed pass

## Export

**Export gate**:
The decision that blocks publication when surfaced validation results are blocking unless an explicit force-export choice bypasses them.
_Avoid_: publish gate, export check

**PPT-ready SVG**:
An SVG prepared for PowerPoint editing, with ordinary text preserved as text and typography chosen to resist reflow after font substitution.
_Avoid_: PPT export mode, PowerPoint file
