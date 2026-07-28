# Output contract

Run directory layout and output formats (plan section 13).

## Run directory

```text
runs/2026-07-28_figure-01/
├── inputs/
├── plans/
│   ├── figure_plan.json
│   ├── plot_spec.json
│   └── layout_wireframe.svg
├── prompts/
├── assets/
├── plots/
├── vectors/
├── validation/
├── exports/
│   ├── figure.png
│   ├── figure.svg
│   ├── figure.pdf
│   └── figure.pptx
├── asset_manifest.json
├── style_bible.json
├── run_state.json
└── generation_report.md
```

PPTX is optional. PNG, SVG, and PDF are default formal outputs.

## Reproducibility

- Preserve the exact plotted data as `data_used.csv`.
- Record model ID, Endpoint ID, prompt, reference hashes, dimensions, seed (when
  available), parameters, and timestamp for every AI asset.
- Do not promise pixel-identical reproduction for AI images.
- Require exact reproducibility for Python and SVG results.

## Versioned schemas

Every core document includes `"schema_version": "1.0"`. Implement migration
support before introducing a breaking schema version.
