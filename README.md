

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
  <a href="https://www.volcengine.com/product/ark"><img src="https://img.shields.io/badge/Ark-Volcengine-red" alt="Ark"></a>
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
| 🎨 | **AI Assets** | Ark image model generates isolated visual elements (device schematics, etc.) with auto background removal |
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

### Configure Ark (optional)

```bash
export ARK_API_KEY="<key>"
export ARK_API_KEY_CODING="<coding key>"
export ARK_IMAGE_GENERATE="<model id>"
export ARK_IMAGE_EDIT="<model id>"
export ARK_VISION_ANALYZE="<model id>"
export ARK_VISION_VALIDATE="<model id>"
```

> Local-only plotting? Skip this and run `./install.sh --without-ark`

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
│   ├── ark/             # Ark client + transport (mock/real)
│   ├── plotting/        # Plot specs, data, recipes, renderer
│   ├── validation/      # Geometry rules + VLM review + evidence
│   ├── assembly/        # Figure composition
│   └── export/          # PNG/SVG/PDF/PPTX
├── schemas/             # 6 versioned JSON Schemas
├── templates/           # Default config + plot recipes
├── references/          # Routing/workflow/Ark docs
└── tests/               # unit / integration / e2e
```

## License

[MIT](./LICENSE)
