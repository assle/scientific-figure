# User guide

This guide covers the public installation, configuration, figure workflow, and
removal paths. Internal architecture belongs in [`CONTEXT.md`](../CONTEXT.md) and
the ADRs; maintainer publishing belongs in
[`operations/release-and-local-activation.md`](operations/release-and-local-activation.md).

## Installation choices

Requirements are Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

For the complete Codex integration, including the optional configuration app:

```bash
./install.sh --codex --release latest --with-gui
```

For headless Codex, omit `--with-gui`. For the Core runtime and CLI without an
Agent integration:

```bash
./install.sh --runtime-only --release latest
```

Use `--release vX.Y.Z` to pin an exact published release, or `--bundle FILE` to
activate a local Product bundle. A local bundle requires the release-generated
`SHA256SUMS` in the same directory.

The default Unix launcher is `~/.local/bin/scientific-figure`. Installation does
not modify shell startup files, so add that directory to `PATH` if necessary.

## Configuration

### Configuration layers

The effective configuration is merged from lowest to highest priority:

1. packaged defaults;
2. global configuration;
3. project configuration;
4. explicit per-run overrides.

The global file is
`$XDG_CONFIG_HOME/scientific-figure-builder/config.yaml`, defaulting to
`~/.config/scientific-figure-builder/config.yaml` on Unix. Set
`SCIENTIFIC_FIGURE_CONFIG` to use another absolute file.

`scientific-figure init PROJECT_DIR` creates project-local files under
`PROJECT_DIR/.scientific-figure/`. These files contain no credentials and may be
edited to override canvas, export, model, Provider, and validation defaults for
that project.

### Configuration app

Install the app later if it was omitted initially:

```bash
scientific-figure install-gui
scientific-figure gui
```

In the app:

1. Create a Provider and select its protocol type.
2. Enter the endpoint and only the capabilities it actually supports.
3. Save the API key to the system credential store or name an environment
   variable with `key_env`.
4. Bind model roles to that Provider and fixed model or endpoint IDs.
5. Run the connection test explicitly when needed.

Opening or saving configuration does not contact a Provider. The connection test
uses the current draft only when requested.

### Provider types and model roles

Supported Provider types are:

| Type | Supported work |
| --- | --- |
| `openai` | Reasoning, vision, image generation, and declared image-edit capabilities |
| `anthropic` | Reasoning and vision through the Messages API |
| `dashscope` | Native image generation/editing only |

Model roles are `phase_reasoning` (optional), `image_generate`, `image_edit`
(optional; inherits `image_generate`), `vision_analyze`, and `vision_validate`.
A route is usable only when its Provider type and declared capabilities match the
role.

### Minimal headless example

```yaml
providers:
  openai_main:
    type: openai
    base_url: https://api.example.com/v1
    key_env: OPENAI_API_KEY
    supports_image_edit: true

models:
  phase_reasoning: {provider: openai_main, model: reasoning-model}
  image_generate:  {provider: openai_main, model: image-model}
  vision_analyze:  {provider: openai_main, model: vision-model}
  vision_validate: {provider: openai_main, model: vision-model}
```

Keep API keys out of YAML. Export the named variable in the environment that
launches Codex or the runtime. When no live Provider credential is available, the
runtime uses its deterministic no-network mock transport. That mode is useful for
tests and offline workflow checks, but its assets are not evidence of a real model
call.

## Figure workflow

### Start a run

Give the Agent the scientific goal and the files it may use. Include output
constraints that matter: figure width, language, publication target, style,
required content, and export formats.

```text
Use scientific-figure-builder to create a two-panel figure from results.csv and
diagram-notes.md. Use English labels, a 14 cm full-column width, and export PNG,
SVG, and PDF.
```

The Codex integration exposes two public lifecycle tools: one initializes project
configuration and one advances the figure workflow. Normal work stays inside the
single lifecycle instead of calling rendering helpers in an ad hoc sequence.

### Decision points

The lifecycle moves through Intake, Planning, Execution, Review and repair, and
Export. The Agent follows the returned status and next action:

- answer required clarifications before production starts;
- review the plan or generation summary before paid generation;
- approve, revise the generation choice, or request a targeted repair;
- resume the same operation when a long Provider call is still in progress;
- treat only validated exports as completed artifacts.

Measured values, labels, equations, geometry, assembly, and exports remain
deterministic. Image Providers may own explicitly planned non-quantitative units.
Visual review supplements deterministic checks and cannot override their failures.

### Outputs and resuming

Each run uses its own run directory and persists versioned state, plans, assets,
validation evidence, and exports. Resume the existing operation ID when the
workflow reports `in_progress`; starting a replacement may repeat paid work.
Changes invalidate only affected downstream artifacts, so unrelated valid assets
can be reused.

Default formal exports are PNG, SVG, and PDF. Choose the `ppt` export target when
PowerPoint-editable SVG text is required; `general` favors broad SVG compatibility.

## Updating and diagnostics

```bash
scientific-figure update --latest
scientific-figure status
scientific-figure status --verbose
scientific-figure status --remote
```

`update` keeps the installed Codex/runtime shape and GUI selection unless an
explicit override is supplied. Use `--release vX.Y.Z`, `--with-gui`,
`--without-gui`, `--codex`, or `--runtime-only` only when changing that choice.

Status exit codes are:

| Code | Meaning |
| ---: | --- |
| `0` | Local components are converged. |
| `2` | The new version is on disk; restart Codex to reload running components. |
| `3` | Components are inconsistent, or `--remote` found an update. |
| `4` | The active runtime is missing or unreadable. |

The MCP server and configuration app run on demand. No idle daemon or manual
`start-all` step is required.

## Uninstall

The Native plugin and Core runtime are managed separately. Preview first:

```bash
./uninstall.sh --dry-run
```

Common scopes:

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh                         # Core runtime and CLI
./uninstall.sh --config                # Core runtime, CLI, global config, credentials
./uninstall.sh --all                   # Core plus legacy integration, config, credentials
./uninstall.sh --runtime-only --project DIR
```

The default runtime uninstall keeps global Provider configuration and credentials.
Credential cleanup removes only entries referenced by this product's global config;
if secure-store cleanup fails, the configuration is retained.
