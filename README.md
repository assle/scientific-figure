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
| Lifecycle MCP server | Exposes project initialization and lifecycle advancement |
| Core runtime | Performs plotting, assembly, validation, and export locally |
| Configuration app | Manages Providers, Model routes, and system credentials |
| Agent integrations | Make the Skill and MCP server discoverable in Codex or OpenCode |

## What it delivers

| | Capability | Result |
|---|---|---|
| 📊 | Deterministic plots | CSV-backed line, scatter, bar, heatmap, error-bar, and multipanel figures |
| 🎨 | Provider-neutral AI assets | Isolated, non-quantitative raster assets with provenance and background removal |
| 🧩 | Precise assembly | Python/SVG composition with editable labels, arrows, and equations |
| ✅ | Two-layer validation | Authoritative geometry checks enriched by multimodal review |
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
- **Credentials & Connection** stores API Keys in the operating-system Keyring and
  tests the current unsaved draft only when the user clicks the button.
- **Model routes** bind `vision_analyze`, `image_generate`, optional `image_edit`,
  and `vision_validate` to a Provider and fixed model identifier.
- With no Provider configured, route selectors stay disabled and lead directly to
  the Provider creation flow.

## Quick start

### 1. Install the Core runtime and Codex plugin

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure
./install.sh --runtime-only --with-gui
codex plugin marketplace add .
codex plugin add scientific-figure-builder@scientific-figure
```

The Core runtime command installs deterministic engines, the lifecycle MCP server,
the CLI, and the optional Configuration app without editing Codex configuration.
The repo marketplace then lets Codex install and own the Native plugin. Omit
`--with-gui` for a headless Core runtime. OpenCode users install its separate
Agent integration with `./install.sh --opencode-only`.

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
and style in a Figure brief, then shows the Figure plan and wireframe before
paid generation. Calling Agent commands resume from the Orchestrator's next
action instead of manually sequencing low-level tools.

## The core rule

```text
Exact data, axes, equations, labels, and geometry  →  Python / SVG
Isolated non-quantitative visual assets            →  configured image Provider
Final composition and export                       →  deterministic local pipeline
```

AI image models never draw data plots or the final compound figure. Deterministic
findings remain authoritative; a vision model may enrich them but cannot turn a
failed geometry check into a pass.

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

models:
  vision_analyze:  {provider: vision_provider, model: vision-model}
  image_generate:  {provider: image_provider,  model: image-model}
  vision_validate: {provider: vision_provider, model: vision-model}
```

Omit `image_edit` to inherit `image_generate`. A Keyring-backed credential takes
precedence over its environment fallback.

## Export targets

| Target | Best for | SVG text |
|---|---|---|
| `general` | Publishing, browsers, vector tools | Converted to portable paths |
| `ppt` | PowerPoint editing and ungrouping | Preserved as editable text |

## Installation options

```bash
./install.sh --runtime-only        # Core and CLI for the Native Codex plugin
./install.sh --runtime-only --with-gui
./install.sh                       # legacy Codex + OpenCode integration bundle
./install.sh --with-gui            # legacy bundle plus Configuration app
./install.sh --codex-only
./install.sh --opencode-only
./install.sh --project /path/to/project
./install.sh --verify            # verify Core; report GUI status
./install.sh --verify --with-gui # require both Core and GUI
```

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

<details>
<summary><strong>Uninstall safely</strong></summary>

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh                  # keep user config and Keyring credentials
./uninstall.sh --config         # also clean referenced Keyring entries
./uninstall.sh --project DIR    # remove one project-scoped integration
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

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uv run --extra gui python -m figure_tools gui
```

Useful references:

- [Domain vocabulary](./CONTEXT.md)
- [Provider interfaces](./scientific-figure-builder/references/provider-interfaces.md)
- [Workflow details](./scientific-figure-builder/references/workflow-details.md)
- [Security policy](./SECURITY.md)
- [GUI platform verification](./docs/verification/gui-platforms.md)

## License

[MIT](./LICENSE)
