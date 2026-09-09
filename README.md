<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
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
  Build reproducible, publication-ready scientific figures through one governed workflow.
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="Publication-ready compound scientific figure" width="820">
</p>

Scientific Figure Builder helps an agent turn a clarified request into source-backed
plots and assets, an assembled figure, validation evidence, and exportable outputs.
Measured data stays on deterministic Python/SVG paths; configured model providers
handle eligible image generation and visual analysis.

## Highlights

- Reproducible line, scatter, bar, heatmap, error-bar, and multipanel plots.
- Structure-first mechanism figures with addressable nodes and connectors.
- Explicit planning and approval before paid image generation.
- Deterministic assembly, layered validation, targeted repair, and resumable runs.
- PNG, SVG, and PDF export, with optional PowerPoint-friendly SVG/PPTX output.
- A native Codex plugin, local runtime, CLI, and optional configuration app.

## Requirements

- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- Codex for the native agent workflow. The Core runtime can also be installed alone.

## Install

Clone the repository and activate the latest published Codex release:

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure
./install.sh --codex --release latest --with-gui
```

Omit `--with-gui` on a headless machine. To install only the Core runtime and CLI:

```bash
./install.sh --runtime-only --release latest
```

If the launcher is not on your shell path, invoke it as
`~/.local/bin/scientific-figure` or add `~/.local/bin` to `PATH`.

## Configure

Open the optional configuration app:

```bash
scientific-figure gui
```

Create Providers first, then bind the model roles you need. API keys saved by the
app go to the operating-system credential store, not the YAML configuration.
Headless systems can configure provider `key_env` fields and supply credentials as
environment variables.

Initialize project-local settings when a project needs to override global defaults:

```bash
scientific-figure init /path/to/project
```

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

The workflow advances through:

```text
intake → planning → approval → execution → review and repair → export
```

The runtime pauses only when it needs clarification, plan approval, a repair choice,
or acknowledgement of a generation summary. A summary or preview is not a completed
figure; final artifacts are reported only after validation and export.

## Update and status

```bash
scientific-figure update --latest
scientific-figure status
```

An update preserves provider configuration, credential references, project data,
and run artifacts. If `status` reports `restart_required`, save active work and
fully restart Codex so new MCP/GUI processes load the activated runtime.

Use `scientific-figure status --remote` when you explicitly want to check GitHub for
a newer release; ordinary status checks are local.

## Uninstall

Preview what the source uninstaller would remove:

```bash
./uninstall.sh --dry-run
```

Then choose the intended scope:

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh              # Core runtime and CLI; keep configuration
./uninstall.sh --all        # Also remove global config and referenced credentials
```

The native plugin and the Core runtime have separate lifecycles. Remove both for a
complete uninstall. The uninstaller preserves global configuration and credentials
unless `--all` or `--config` is explicit.

## Documentation

- [User guide](docs/user-guide.md): configuration, workflow, updates, and removal.
- [Release and local activation](docs/operations/release-and-local-activation.md):
  maintainer release gates and runtime activation semantics.
- [Product vocabulary](CONTEXT.md): canonical domain and lifecycle terms.
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md).
- [Architecture decisions](docs/adr/).

## Development

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uvx pyright --pythonpath .venv/bin/python figure_tools install
```

The authoritative Skill lives in `scientific-figure-builder/SKILL.md`. After changing
it, run `python3 scripts/sync_plugin_bundle.py`; do not edit the generated plugin copy
directly.

## License

[MIT](./LICENSE)
