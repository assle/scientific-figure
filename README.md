

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

### Install

```bash
cd scientific-figure-builder
uv sync
cd ..
./install.sh
```

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), [OpenCode](https://opencode.ai/)

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
