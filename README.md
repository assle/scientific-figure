<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="820">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/GUI-optional-3B6FF5" alt="Optional GUI">
  <a href="https://github.com/assle/scientific-figure/releases/latest"><img src="https://img.shields.io/github/v/release/assle/scientific-figure?label=release" alt="Latest release"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License"></a>
</p>

<p align="center">
  <strong>From a clarified scientific request to a validated, publication-ready export.</strong>
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="Publication-ready compound scientific figure" width="820"><br>
  <sub>Illustrative composite output from synthetic demonstration data.</sub>
</p>

Scientific Figure Builder helps an agent turn a clarified request into source-backed
plots and assets, an assembled figure, validation evidence, and exportable outputs.
Measured data stays on deterministic Python/SVG paths; configured model providers
handle eligible image generation and visual analysis.

## Requirements

- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- Codex for the native agent workflow. The Core runtime can also be installed alone.

## What it delivers

- Reproducible line, scatter, bar, heatmap, error-bar, and multipanel plots.
- Structure-first mechanism figures with addressable nodes and connectors.
- Explicit planning and approval before paid image generation.
- Deterministic assembly, layered validation, targeted repair, and resumable runs.
- PNG, SVG, and PDF export, with optional PowerPoint-friendly SVG/PPTX output.
- A native Codex plugin, local runtime, CLI, and optional configuration app.

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="250"><br><sub>Error-aware line plot</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="250"><br><sub>Efficiency landscape</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="330"><br><sub>Multipanel composition</sub></td>
    </tr>
  </table>
</p>

<p align="center">
  <sub>Illustrative outputs generated from synthetic demonstration data; they are not scientific evidence.</sub>
</p>

## Quick start

The working directory matters for the installation and source commands below.
Every command is shown in the directory where it should be run.

### 1. Install a published release

Run these commands from the repository root after cloning:

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure          # repository root; contains ./install.sh
./install.sh --codex --release latest --with-gui
```

`./install.sh` is a repository script, so run it from the folder that contains it.
Omit `--with-gui` on a headless machine. To install only the Core runtime and CLI:

```bash
./install.sh --runtime-only --release latest
```

### 2. Use the installed CLI from any directory

After installation, the `scientific-figure` launcher is independent of the
repository. These commands work from any project directory:

```bash
scientific-figure status
scientific-figure gui
scientific-figure update --latest
```

If the launcher is not on your shell path, invoke `~/.local/bin/scientific-figure`
or add `~/.local/bin` to `PATH`. You do not need to `cd` into the repository to
run these installed commands.

### 3. Run the GUI from a source checkout

For development, run these commands inside `scientific-figure-builder/`, the folder
that contains `pyproject.toml`:

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui python -m figure_tools gui
```

A source checkout does not install the `scientific-figure` launcher by itself.
Use the command above for the current source tree, or complete step 1 and use
`scientific-figure gui` after installation.

## Configuration app

The native Qt Quick app manages Providers, Model routes, and system credentials.
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
    <td align="center"><sub>Endpoints, protocols, and declared capabilities</sub></td>
    <td align="center"><sub>System credentials and explicit connection testing</sub></td>
  </tr>
</table>

- Create Providers first, then bind the Model roles you need.
- API keys saved by the app go to the operating-system credential store, not YAML.
- Headless environments can configure provider `key_env` fields and supply
  credentials as environment variables.
- Initialize project-local overrides with `scientific-figure init /path/to/project`.

Configuration precedence is: packaged defaults → global configuration → project
configuration → per-run overrides. See the [user guide](docs/user-guide.md) for
provider types, model roles, file locations, and a minimal YAML example.

## Workflow

Ask Codex to use the installed skill and describe the source data, intended figure,
language, dimensions or publication target, and required export formats:

```text
Use scientific-figure-builder to create a publication-ready multipanel figure
from data.csv. Export PNG, SVG, and PDF, and keep the SVG editable in PowerPoint.
```

<p align="center">
  <img src="assets/workflow.svg" alt="Intake, planning, approval, execution, review and repair, then export" width="900">
</p>

Measured data and quantitative plots stay on deterministic Python/SVG paths.
Non-quantitative figure units can use a configured Provider route. Final
composition, validation, repair, and export remain deterministic and local.
The runtime pauses only when it needs clarification, plan approval, a repair
choice, or acknowledgement of a generation summary.

## Update, status, and uninstall

Use installed commands from any directory:

```bash
scientific-figure update --latest
scientific-figure status
```

An update preserves provider configuration, credential references, project data,
and run artifacts. If `status` reports `restart_required`, save active work and
fully restart Codex so new MCP/GUI processes load the activated runtime. Use
`scientific-figure status --remote` only when you explicitly want to check GitHub
for a newer release.

Preview the source uninstaller from the repository root, then choose the intended
scope:

```bash
./uninstall.sh --dry-run
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh              # Core runtime and CLI; keep configuration
./uninstall.sh --all        # Also remove global config and referenced credentials
```

The native plugin and the Core runtime have separate lifecycles. Remove both for a
complete uninstall. The uninstaller preserves global configuration and credentials
unless `--all` or `--config` is explicit.

## Documentation

- [User guide](docs/user-guide.md): installation, configuration, workflow, updates,
  and removal.
- [Release and local activation](docs/operations/release-and-local-activation.md):
  maintainer release gates and runtime activation semantics.
- [Product vocabulary](CONTEXT.md): canonical domain and lifecycle terms.
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md).
- [Architecture decisions](docs/adr/).

## Development

Run development commands from `scientific-figure-builder/`:

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uvx pyright --pythonpath .venv/bin/python figure_tools install
```

The authoritative Skill lives in `scientific-figure-builder/SKILL.md`. After changing
it, run the synchronization script from the repository root:

```bash
python3 scripts/sync_plugin_bundle.py
```

After a configuration-app visual change, regenerate its README screenshots from the
repository root:

```bash
uv run --frozen --directory scientific-figure-builder --extra gui \
  python ../scripts/capture_readme_screenshots.py
```

The example figures can be regenerated independently with the same synthetic demo
data:

```bash
uv run --frozen --directory scientific-figure-builder \
  python ../scripts/generate_readme_examples.py
```

## License

[MIT](./LICENSE)
