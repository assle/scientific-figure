# Output contract

Run directory layout and output formats (plan section 13).

## Run directory

```text
runs/2026-07-28_figure-01/
├── inputs/
├── plans/
│   ├── figure_brief.json
│   ├── figure_plan.json
│   ├── figure_plan.v<N>.json
│   ├── plot_spec.json
│   ├── execution_result.json
│   ├── repair_plan.json
│   ├── export_result.json
│   └── layout_wireframe.svg
├── prompts/
│   ├── intake.json / intake.txt
│   ├── planning.json / planning.txt
│   └── review_and_repair.json / review_and_repair.txt
├── assets/
├── plots/
│   └── <asset_id>/
│       ├── plot.png
│       ├── plot.svg
│       ├── plot.pdf
│       ├── data_used.csv
│       └── layout_manifest.json      # source-level layout (plan section 8)
├── vectors/
├── validation/
│   ├── validation_report.json        # final report (back-compat name)
│   ├── final.json                    # final report (canonical)
│   ├── root_cause_report.json        # only when blocking errors occur
│   └── evidence/                     # localised failure crops (plan section 13)
├── assembly/
│   ├── figure.png
│   ├── figure.svg
│   ├── figure.pdf
│   └── layout_manifest.json          # assembly-level layout (plan section 9)
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

## Image QA outputs

- **Layout manifests** (`layout_manifest.json`) record real element bounding
  boxes in the top-left pixel convention. A plot-level manifest is emitted by
  `render_plot`; an assembly-level manifest is emitted by `compose_assets`.
- **Validation report** (`validation/final.json`) carries deterministic +
  geometry + multimodal checks. Failing layout checks include `bbox`,
  `element_ids`, `confidence`, `method`, `evidence_path`, and `repair_action`.
- **Evidence crops** (`validation/evidence/<check_id>_<n>.png`) are enlarged,
  annotated regions for each localised failure; they are audit aids, not formal
  exports.

## Reproducibility

- Preserve the exact plotted data as `data_used.csv`.
- Record model ID, Endpoint ID, prompt, reference hashes, dimensions, seed (when
  available), parameters, and timestamp for every AI asset.
- Do not promise pixel-identical reproduction for AI images.
- Require exact reproducibility for Python and SVG results.

## Versioned schemas

Every core document includes `"schema_version": "1.0"`. Implement migration
support before introducing a breaking schema version.
