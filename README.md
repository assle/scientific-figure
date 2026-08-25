

<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?logo=opensourceinitiative&logoColor=white" alt="License"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-Required-purple?logo=astralshuv&logoColor=white" alt="uv"></a>
  <a href="https://opencode.ai/"><img src="https://img.shields.io/badge/OpenCode-Ready-orange?logo=data:image/svg+xml;base64,&logoColor=white" alt="OpenCode"></a>
  <img src="https://img.shields.io/badge/Providers-Configurable-blue" alt="Configurable providers">
  <img src="https://img.shields.io/badge/Plots-Reproducible-success" alt="Reproducible">
</p>

---

## Overview

Transform natural-language requests into **reproducible, publication-quality** scientific figures. Data plots are rendered deterministically by Python/SVG; AI image models only generate isolated non-quantitative assets. Every output is byte-for-byte reproducible across runs.

<p align="center">
  <img src="assets/example_compound.png" alt="Compound Figure Example" width="640">
</p>

## Features

| | Feature | Description |
|---|---|---|
| 📊 | **Deterministic Plots** | Line / scatter / bar / heatmap / error bar / multipanel — CSV to figure, byte-reproducible |
| 🎨 | **AI Assets** | Configurable image models generate isolated visual elements (device schematics, etc.) with auto background removal |
| 🏷️ | **SVG Labels** | Arrows, equations, annotations — all deterministic |
| 🧩 | **Auto Assembly** | Multi-element z-order composition → PNG / SVG / PDF |
| 🎯 | **Export Targets** | `general` for portable path-based text, `ppt` for editable PowerPoint-friendly SVG |
| ✅ | **Two-Layer Validation** | Deterministic geometry rules + multimodal VLM review; blocking errors halt export |
| 🔄 | **Reproducible Runs** | Versioned run directory, caching, checkpoint resume |

## Quick Start

### Choose an export target

SVG output supports two targets:

- `general` (default): text is rendered as paths for maximum cross-tool compatibility.
- `ppt`: text stays editable as `<text>` and is normalized for PowerPoint ungrouping/convert-to-shape.

Set it in the project configuration:

```yaml
export:
  export_target: ppt
```

Or override it for a single tool call or run with `export_target: "ppt"`.

### Choose a figure width

When no width is specified, the skill asks which common publication width to
use:

- Half-column: 6.5 cm
- Full-column: 14 cm

You can also set it in the structured request:

```yaml
figure_width_cm: 6.5
```

Height is derived from the default canvas aspect ratio unless a custom height
is supplied.

### Choose language and style

When not specified, the skill asks before planning:

- Text language: Chinese (`zh`) or English (`en`)
- Figure style: `default` publication style or a custom style reference

Set them in the structured request when you already know them:

```yaml
language: zh
style: default
```

### Install

Install once for **both OpenCode and Codex** (global):

```bash
./install.sh
```

Or install directly from GitHub without cloning manually:

```bash
curl -fsSL https://raw.githubusercontent.com/assle/scientific-figure/main/install.sh | sh
```

This copies the skill, command, and private runtime into your user-level
OpenCode and Codex directories. You do **not** need to copy the repository into
each project. The installer writes both integrations by default.

To install only for one project instead:

```bash
./install.sh --project /path/to/your-project
```

Install only one agent:

```bash
./install.sh --opencode-only
./install.sh --codex-only
```

Global install paths are:

- Skill: `~/.config/opencode/skills/scientific-figure-builder`
- Command: `~/.config/opencode/commands/scientific-figure.md`
- Codex skill: `~/.codex/skills/scientific-figure-builder`
- Codex config: `~/.codex/config.toml`
- Runtime: `~/.local/share/scientific-figure-builder`

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), and whichever of
[OpenCode](https://opencode.ai/) or Codex you use. Run the installer once from a
checkout of this repository; the checkout does not become part of your project.

## Install

Run once from a checkout of this repository:

```bash
./install.sh
```

Target only one agent, or install into a specific project:

```bash
./install.sh --target codex         # or: --target opencode
./install.sh --project /path/to/project
```

**What the installer does.**

- Creates a private, self-contained runtime at `~/.local/share/scientific-figure-builder/`
  (a virtualenv with the package, schemas, templates, and references).
- Installs the **skill** into your agent(s) so they can invoke the tool:
  - Codex: `~/.codex/skills/scientific-figure-builder/`
  - OpenCode: `~/.config/opencode/skills/scientific-figure-builder/`
- Adds an OpenCode **slash command** at `~/.config/opencode/commands/scientific-figure.md`.
- Registers the MCP **server entry** (launches `figure_tools.server`):
  - Codex: `[mcp_servers.scientific-figure]` in `~/.codex/config.toml`
  - OpenCode: `mcp.scientific-figure` in `~/.config/opencode/opencode.json`
- Global installs create `~/.local/bin/scientific-figure`; project installs do not
  create a global launcher. If that directory is not on `PATH`, installation
  prints the exact directory to add.
- Forwards the configured provider environment variables (every provider's
  `key_env` plus the `SCI_FIG_*` model-role overrides) to the MCP host.
- Backs up any existing config before editing.

No API keys are written to disk; credentials use the operating-system
credential store when configured and otherwise stay in environment variables.
Choose which providers to use under "Configure model providers" below.

## Uninstall

Remove the installed software and its MCP entries without touching this
repository or unrelated configuration:

```bash
./uninstall.sh                        # global install
./uninstall.sh --config               # also remove ~/.config/scientific-figure-builder/
./uninstall.sh --all                  # global + user config
./uninstall.sh --project /path/to/project   # a per-project install
./uninstall.sh --dry-run              # preview without changing anything
```

**What the uninstaller removes.**

- The private runtime: `~/.local/share/scientific-figure-builder/`
- Installed skills:
  - `~/.codex/skills/scientific-figure-builder/`
  - `~/.config/opencode/skills/scientific-figure-builder/`
- The OpenCode slash command: `~/.config/opencode/commands/scientific-figure.md`
- The MCP server entries (only `scientific-figure`; other servers are preserved):
  - Codex: `[mcp_servers.scientific-figure]` in `~/.codex/config.toml`
  - OpenCode: `mcp.scientific-figure` in `~/.config/opencode/opencode.json`
- The launcher only when it carries the tool's marker; an unrelated same-name
  file is never overwritten or removed.
- With `--config`: the user config directory `~/.config/scientific-figure-builder/`
  after attempting cleanup of only its referenced Keyring credentials.
- With `--project DIR`: the per-project `.opencode/` and `.codex/` skill, command,
  and MCP entries for that project install

Other agent config, projects, and this repository are left untouched. Removed
directories can be restored by re-running `./install.sh`.

### Configure model providers (optional)

For a native configuration window, run `python -m figure_tools gui` from the
installed runtime (or `uv run --extra gui --directory scientific-figure-builder
python -m figure_tools gui` from this checkout). It edits the user-scoped models and
providers file without starting a browser or local server. Provider API keys
remain in the operating-system credential store; headless and CI use continues
to work with `key_env` environment variables.

The Provider page supports add/rename/delete, OpenAI and Anthropic advanced
fields, and password-mode API Key updates. “Test connection” is explicitly
user-triggered, uses the current unsaved draft and a deterministic minimal image,
and prefers a bound vision role. A generation-only test shows a cost warning
first. Omitting `image_edit` inherits `image_generate`.

Each model role is assigned to a provider, so different steps can use different
vendors. Configure globally in `~/.config/scientific-figure-builder/config.yaml`
and override per project in `.scientific-figure/project.yaml`. The `SCI_FIG_*`
environment variables override model ids; each provider's `key_env` names the
environment fallback for its credential. A configured `credential_id` in the
system store takes precedence over that fallback.

A provider speaks one of two wire dialects: `openai` — `/images/generations`
for generation plus `/responses` for vision; `anthropic` — `/messages` for
vision only. Point `base_url` at the API root, not a complete operation URL.

```yaml
# ~/.config/scientific-figure-builder/config.yaml (no API keys)
providers:
  deepseek:
    type: openai
    base_url: https://api.deepseek.com/           # DeepSeek multimodal via /responses
    key_env: DEEPSEEK_API_KEY
  ark_seedream:
    type: openai
    base_url: https://ark.cn-beijing.volces.com/api/plan/v3  # Seedream via /images/generations
    key_env: ARK_API_KEY
    supports_image_edit: true
models:
  image_generate: {model: "<Seedream model id>", provider: ark_seedream}
  vision_analyze: {model: "deepseek-v4-flash-vision-exp", provider: deepseek}
  vision_validate: {model: "deepseek-v4-flash-vision-exp", provider: deepseek}
```

`image_generate` must be a true image-generation model. `vision_analyze` and
`vision_validate` are multimodal (image-reading) models and may be the same
vendor as the analysis step. `image_edit` is optional and falls back to
`image_generate`. Plots, labels, equations, and SVG elements are rendered
deterministically and never sent to a model. Credentials are never stored in
config, logs, artifacts, or manifests; the installer forwards every configured
`key_env` to the MCP host automatically. For a local checkout, point
`SCIENTIFIC_FIGURE_CONFIG` at your own config file instead of editing
`~/.config/...`.

### Use in OpenCode

```text
Use scientific-figure-builder to create a line plot from data.csv
```

Or with commands:

```bash
/scientific-figure init
/scientific-figure plan Create a multipanel figure from data.csv
/scientific-figure run
/scientific-figure validate
/scientific-figure export
```

## Examples

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="280"><br><sub>Line plot</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="280"><br><sub>Heatmap</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="280"><br><sub>Multipanel</sub></td>
    </tr>
  </table>
</p>

## Development

```bash
cd scientific-figure-builder
uv sync
uv run pytest
```

The optional PowerPoint end-to-end test opens the local Microsoft PowerPoint
application and verifies that an `export_target=ppt` SVG can be inserted,
converted, and ungrouped:

```bash
RUN_POWERPOINT_E2E=1 uv run pytest tests/e2e/test_powerpoint_import.py -q
```

The first run may require granting PowerPoint access to the test directory in
the macOS permission prompt.

## Project Structure

```
scientific-figure-builder/
├── figure_tools/        # Core Python package
│   ├── providers/       # Provider transports + client (OpenAI/Anthropic)
│   ├── plotting/        # Plot specs, data, recipes, renderer
│   ├── validation/      # Geometry rules + VLM review + evidence
│   ├── assembly/        # Figure composition
│   └── export/          # PNG/SVG/PDF/PPTX
├── schemas/             # 6 versioned JSON Schemas
├── templates/           # Default config + plot recipes
├── references/          # Routing/workflow/provider docs
└── tests/               # unit / integration / e2e
```

## License

[MIT](./LICENSE)
