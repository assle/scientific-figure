<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/GUI-Qt_Quick-3B6FF5" alt="Qt Quick GUI">
  <img src="https://img.shields.io/badge/Providers-Configurable-blue" alt="Configurable providers">
  <img src="https://img.shields.io/badge/Plots-Reproducible-success" alt="Reproducible plots">
  <img src="https://img.shields.io/badge/version-0.2.0--dev-orange" alt="Development version 0.2.0">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License"></a>
</p>

<p align="center">
  Turn a clarified scientific request into reproducible assets, an assembled figure,
  validation evidence, and publication-ready exports.
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="Publication-ready compound scientific figure" width="820">
</p>

## Product and delivery

Scientific Figure Builder is the open-source product, not a synonym for any one
of its components. It combines a Workflow Skill, a local lifecycle MCP server,
the deterministic Core runtime, a CLI, and a native Configuration app.

The current `0.2.0` development line ships a **Native Codex plugin**, an OpenCode
Agent integration, and an independently versioned Core runtime. The Native plugin
owns Codex discovery, enablement, upgrade, and removal of its Workflow Skill and
MCP declaration; the separate Core runtime keeps deterministic execution and the
optional Configuration app outside the host plugin cache.

| Component | Responsibility |
|---|---|
| Workflow Skill | Teaches the Calling Agent when and how to run the workflow |
| Lifecycle MCP server | Exposes exactly `initialize_figure_project` and `advance_figure_workflow` |
| Core runtime | Owns lifecycle state, execution, plotting, assembly, validation, and export locally |
| Configuration app | Manages Providers, Model routes, and system credentials |
| Agent integrations | Make the Skill and MCP server discoverable in Codex or OpenCode |

## Architecture and lifecycle

There is one public lifecycle path and one authority for phase transitions:

```text
Calling Agent
  → Lifecycle MCP server (2 public tools)
    → Orchestrator (the only lifecycle authority)
      ├─ Phase worker → schema-governed Phase artifact
      ├─ Figure Planning Module
      │  └─ Figure Graph → Solved layout → SVG blueprint
      │     → Generation Conditions + structure questions
      ├─ Run Store + Run Invalidator → atomic persistence and precise reuse
      └─ Figure Execution Module
         ├─ Python plots and SVG/text
         ├─ Provider-routed isolated raster assets
         └─ deterministic connectors/groups → assembly
            → layered validation → localized repair → export
```

The MCP server is a thin stdio Adapter. It does not publish plotting, Provider,
validation, or export helpers as hidden product tools. `advance_figure_workflow`
validates its input and output schemas, constructs one Runtime Context, and asks
the Orchestrator to advance until the next user decision or completion.

| Deep module | Owns |
|---|---|
| Orchestrator | Intake, Planning, Execution, Review and repair, Export, approvals, retries, resume, and the Export gate |
| Figure Planning Module | Figure Graph, Solved layout, editable blueprint, structure questions, Style Bible, and Generation Conditions before approval |
| Figure Execution Module | Approved Generation routes, Style-anchor conditions, candidate selection, deterministic assembly, validation inputs, and publication |
| Run Store | Run-directory structure, atomic JSON commit, schema validation, canonical hashes, references, and safe loads |
| Run Invalidator | Exact downstream invalidation for Figure brief/plan changes, repairs, assembly changes, and export-only reruns |
| Provider Configuration | Provider types, legacy migration, type-specific fields, Model role catalog, inheritance, and Route compatibility |
| Runtime Context Factory | Effective configuration, credentials, transport, Provider client, budget, cache, Run state, and Phase worker |

Run reuse is content-based rather than file-existence-based. Schema-invalid,
hash-mismatched, or externally replaced artifacts are not reused. Layout-only
plan revisions preserve valid paid raster assets; Python/SVG repairs rerender
their source-derived outputs; image edits preserve unrelated deterministic and
paid assets.

## What it delivers

| | Capability | Result |
|---|---|---|
| 📊 | Deterministic plots | CSV-backed line, scatter, bar, heatmap, error-bar, and multipanel figures |
| 🧠 | Structure-first mechanism figures | Addressable nodes, named ports, typed directed edges, groups, constraints, and editable SVG blueprints |
| 🎨 | Provider-neutral AI assets | Isolated, non-quantitative raster assets with provenance and background removal |
| 🧩 | Precise assembly and repair | Asset-level placement, port-bound connectors, exact vector labels/equations, masked edits, and rollback |
| ✅ | Layered validation | Rendered graph recovery, exact source/OCR text and formulas, geometry, Publication profiles, and multimodal review |
| 📦 | Publication export | PNG, SVG, PDF, plus optional PowerPoint-friendly SVG/PPTX |

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="280"><br><sub>Reproducible line plot</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="280"><br><sub>Heatmap with deterministic data mapping</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="330"><br><sub>Multipanel composition</sub></td>
    </tr>
  </table>
</p>

## Visual model routing

The native Qt Quick app manages Global Model routes, Providers, and credentials.
It does not open a browser, start a local web server, or contact a Provider while
opening or saving configuration.

<p align="center">
  <img src="assets/gui-model-routes.png" alt="Model role routing screen" width="920">
</p>

<table>
  <tr>
    <td width="50%"><img src="assets/gui-providers.png" alt="Provider endpoint and capability configuration"></td>
    <td width="50%"><img src="assets/gui-credentials.png" alt="Keyring credential and connection testing"></td>
  </tr>
  <tr>
    <td align="center"><sub>Endpoints, protocols, and capabilities</sub></td>
    <td align="center"><sub>Keyring credentials and explicit connection testing</sub></td>
  </tr>
</table>

- **Providers** handles endpoint CRUD, wire dialects, and optional capabilities.
- **Provider capabilities** explicitly declare reference images, multiple
  references, mask editing, structure control, native alpha, seeds, and
  candidate batches; unsupported controls fail instead of being ignored.
- **Credentials & Connection** stores API Keys in the operating-system Keyring and
  tests the current unsaved draft only when the user clicks the button.
- **Model routes** bind optional `phase_reasoning`, `vision_analyze`,
  `image_generate`, optional `image_edit`, and `vision_validate` to a Provider
  and fixed model identifier.
- With no Provider configured, route selectors stay disabled and lead directly to
  the Provider creation flow.

## Quick start

### 1. Install the Core runtime and Codex plugin

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure
./install.sh --codex --with-gui
codex plugin marketplace add .
codex plugin add scientific-figure-builder@scientific-figure
```

The Core runtime command installs deterministic engines, the lifecycle MCP server,
the CLI, and the optional Configuration app without editing Codex configuration.
The repo marketplace then lets Codex install and own the Native plugin. Omit
`--with-gui` for a headless Core runtime. OpenCode users install its separate
Agent integration with `./install.sh --opencode`.

### 2. Configure Providers

```bash
scientific-figure gui
```

If the Core runtime was installed without `--with-gui`, add or upgrade the
Configuration app at any time without reinstalling the Agent integrations:

```bash
scientific-figure install-gui
```

Requesting `gui` before installing the component returns this exact recovery
command and no Python traceback. Core MCP, plotting, validation, and export do
not import Qt and remain available on headless systems.

Create a Provider first, then assign Model roles. API Keys never enter YAML:
Global configuration stores only a stable `credential_id`, while headless and CI
environments can continue using `key_env` environment variables.

### 3. Ask your agent

```text
Use scientific-figure-builder to create a publication-ready multipanel figure
from data.csv. Export PNG, SVG, and PDF, and keep the SVG PowerPoint-friendly.
```

The lifecycle Orchestrator first records export target, figure width, language,
style, and optional Publication profile in a Figure brief. Planning then derives
the Figure Graph, Solved layout, editable SVG blueprint, structure questions,
and Generation Conditions before any paid work. Calling Agent commands resume
from the Orchestrator's next action instead of manually sequencing low-level
tools. Each response contains the current Lifecycle phase, status, next action,
and canonical Artifact references.

## The core rule

```text
Exact data, axes, equations, labels, and geometry  →  Python / SVG
Scientific nodes, phases, ports, and directed flow →  Figure Graph + SVG
Isolated non-quantitative visual assets            →  configured image Provider
Final composition and export                       →  deterministic local pipeline
```

AI image models never draw data plots or the final compound figure. Deterministic
findings remain authoritative; a vision model may enrich them but cannot turn a
failed geometry check into a pass.

## Mechanism-figure workflow

```text
Scientific intent
  → Figure Graph (nodes, ports, typed edges, groups, constraints)
  → Solved layout + editable SVG blueprint
  → Provider-neutral Generation Conditions
  → isolated raster assets + deterministic text/connectors
  → assembled-figure structure/OCR/publication validation
  → layout, connector, vector, or masked-raster patch with rollback
```

Asset bounding boxes are panel-relative when explicitly supplied. Layout-only
changes preserve paid raster assets. Related assets use approved per-group Style
anchors; references are role-tagged as content, style, structure, parent, or
mask and are hash-verified before upload. `nature_research` is available as a
Publication profile for Nature dimensions, typography, editable vectors, and
palette-accessibility checks, while `general` remains the default.

## Minimal Provider configuration

The GUI writes this metadata for you; API Keys are deliberately absent:

```yaml
providers:
  vision_provider:
    type: openai
    base_url: https://api.example.com/v1
    key_env: VISION_API_KEY
  image_provider:
    type: openai
    base_url: https://images.example.com/v1
    key_env: IMAGE_API_KEY
    supports_image_edit: true
    supports_reference_image: true
    supports_multi_reference: true
    supports_mask_edit: true
    supports_structure_control: false
    supports_native_alpha: false
    supports_seed: true
    supports_candidate_batch: false

models:
  vision_analyze:  {provider: vision_provider, model: vision-model}
  image_generate:  {provider: image_provider,  model: image-model}
  vision_validate: {provider: vision_provider, model: vision-model}
```

Omit `image_edit` to inherit `image_generate`. A Keyring-backed credential takes
precedence over its environment fallback. Declare only capabilities the Provider
actually supports; they are compatibility contracts, not hints.

## Export targets

| Target | Best for | SVG text |
|---|---|---|
| `general` | Publishing, browsers, vector tools | Converted to portable paths |
| `ppt` | PowerPoint editing and ungrouping | Preserved as editable text |

## Installation options

```bash
./install.sh                       # default: Core runtime and CLI only
./install.sh --codex              # explicit Native Codex plugin prerequisite
./install.sh --opencode           # Core plus OpenCode integration only
./install.sh --all                # explicit legacy two-host integration
./install.sh --opencode --project /path/to/project
./install.sh --verify             # verify Core only; report GUI status
./install.sh --verify --opencode  # verify Core and OpenCode integration
./install.sh --verify --with-gui  # require Core and GUI
```

Compatibility aliases remain during migration: `--runtime-only` maps to the
default Core target, `--opencode-only` maps to `--opencode`, and
`--codex-only` installs the deprecated manual Codex Skill/config integration.
The supported Codex path is `--codex` followed by the Native plugin install.

OpenCode configuration updates are JSONC-aware. Install, upgrade, and targeted
uninstall edit only `mcp.scientific-figure` (and create the `mcp`/`$schema`
parents when absent), while preserving unrelated field order, indentation, line
and block comments, inline comments, and trailing commas. Invalid JSONC fails
preflight before any install transaction starts.

### Filesystem layout

Code, the private virtual environment, and dependencies live in a versioned
application-payload prefix rather than `XDG_DATA_HOME`:

| Category | Unix default | Windows default |
|---|---|---|
| Global Core runtime | `~/.local/lib/scientific-figure-builder/global/runtimes/<version>` | `%LOCALAPPDATA%\Programs\ScientificFigureBuilder\global\runtimes\<version>` |
| Project Core runtime | `~/.local/lib/scientific-figure-builder/projects/<project-id>/runtimes/<version>` | `%LOCALAPPDATA%\Programs\ScientificFigureBuilder\projects\<project-id>\runtimes\<version>` |
| Global configuration | `$XDG_CONFIG_HOME/scientific-figure-builder/config.yaml` | `%APPDATA%\scientific-figure-builder\config.yaml` |
| Application state root | `$XDG_STATE_HOME/scientific-figure-builder` | `%LOCALAPPDATA%\State\scientific-figure-builder` |
| Application cache root | `$XDG_CACHE_HOME/scientific-figure-builder` | `%LOCALAPPDATA%\Cache\scientific-figure-builder` |
| Launcher | `~/.local/bin/scientific-figure` | `%LOCALAPPDATA%\Programs\ScientificFigureBuilder\bin\scientific-figure.cmd` |

Absolute XDG overrides are honored. `SCIENTIFIC_FIGURE_INSTALL_HOME` overrides
the application-payload prefix and `SCIENTIFIC_FIGURE_BIN_DIR` overrides the
launcher directory. Project paths are hashed only to create an isolated runtime
identity; user projects remain where the user put them.

Each Agent integration points to an exact Product version. Installing a newer
version builds and verifies a new runtime before switching the active-runtime
record, so a failed upgrade leaves the previous runtime and integration usable.
When the old `$XDG_DATA_HOME/scientific-figure-builder` runtime is detected, a
successful Global installation records it as the migration source and retains
it for rollback. A full Global uninstall removes both the versioned runtime
scope and that legacy runtime; a Project uninstall removes only its own scope.

### Transaction and retention

Install and upgrade run as one filesystem transaction per Runtime scope. The
installer performs source, config, launcher, permission, and disk-space preflight;
builds the Core runtime with non-editable package metadata in same-filesystem
staging; validates the CLI and MCP server; then atomically commits runtime, Skill,
launcher, command, host config, and active-runtime metadata. A failure or process
interruption restores replaced paths in reverse order. A scope lock rejects
concurrent installs, while the next safe run removes orphan staging from a dead
installer.

The Delivery Interface is `InstallRequest → InstallResult`. The request carries
target, Runtime scope, Product version, and GUI selection; the result reports
committed, retained, pruned, and logged paths. The CLI only translates flags
into this Interface. OpenCode and deprecated manual Codex delivery are separate
Host delivery Adapters inside the same transaction, while the Native Codex
plugin remains host-managed.

The retention policy keeps the active Product version and at most one previously
verified runtime. Temporary transaction backups are deleted after commit or
rollback. Sanitized transaction logs are stored below the scope's XDG state
directory and capped at 20 entries; they record paths and outcomes, never config
contents or credentials. Uninstall recognizes active locks and will not remove a
runtime while its install transaction is running.

<details>
<summary><strong>Uninstall safely</strong></summary>

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh                    # default: Core runtime and CLI only
./uninstall.sh --opencode         # OpenCode integration only
./uninstall.sh --codex-legacy     # deprecated manual Codex integration only
./uninstall.sh --integrations     # both legacy integrations; keep Core
./uninstall.sh --all              # Core, legacy integrations, config, credentials
./uninstall.sh --runtime-only --project DIR
./uninstall.sh --dry-run
codex plugin marketplace remove scientific-figure # optional: stop listing this repo
```

Native plugin removal deletes its cached Skill and MCP declaration without
creating or leaving a top-level Codex MCP entry. It deliberately preserves the
independent Core runtime, Global configuration, and Keyring credentials. The
source uninstaller removes every version in the selected runtime scope, including
the optional GUI, plus only legacy installer-owned launcher and MCP entries. A
Global uninstall also removes the retained legacy runtime. If Keyring cleanup
fails, user configuration is retained.
</details>

## Versioning

Scientific Figure Builder follows [Semantic Versioning](https://semver.org/).
`scientific-figure-builder/pyproject.toml` is the canonical Product version;
the CLI and Lifecycle MCP server read that installed package version. Check it
with:

```bash
scientific-figure --version
```

The project is currently pre-1.0, so `0.y.z` releases may still refine public
interfaces. `0.2.0` is the current development version; `v0.1.0` remains the
latest fixed release. A release exists only when the repository has an immutable
`vX.Y.Z` Git tag and a matching GitHub Release. Schema, prompt, and recipe
versions are compatibility contracts of their own and do not follow the Product
version automatically.

## Development

### Repository layout

This is a single-context repository: product vocabulary lives in `CONTEXT.md`
and repository-wide architecture decisions live in `docs/adr/`.

```text
.
├── CONTEXT.md                         # Canonical product vocabulary
├── docs/
│   ├── agents/                        # Engineering-skill configuration
│   ├── adr/                           # Repository-wide architecture decisions
│   └── verification/                  # Current platform evidence
├── scientific-figure-builder/         # Canonical Core, Skill resources, and tests
├── plugins/scientific-figure-builder/ # Generated Native plugin snapshot
├── scripts/                            # Repository maintenance
├── assets/                             # README images
├── install.sh                           # Public source-install entry point
└── uninstall.sh                         # Public source-uninstall entry point
```

Edit canonical Skill resources under `scientific-figure-builder/`, then run
`python3 scripts/sync_plugin_bundle.py` from the repository root. Do not edit the
generated Skill copy under `plugins/` directly; the test suite verifies that the
snapshot matches its canonical source.

### Local development

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uv run --extra gui python -m figure_tools gui
uvx pyright --pythonpath .venv/bin/python figure_tools install
```

Useful references:

- [Domain vocabulary](./CONTEXT.md)
- [Security policy](./SECURITY.md)
- [GUI platform verification](./docs/verification/gui-platforms.md)
- [OpenAI plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)

## License

[MIT](./LICENSE)
