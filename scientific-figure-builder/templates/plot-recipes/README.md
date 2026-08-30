# Plot recipes

Plot recipes are deterministic local renderers.

Available recipes:
- `line`
- `scatter`
- `bar`
- `heatmap`
- `error_bar`
- `multipanel`

Each recipe is a fixed, tested renderer that consumes a `plot_spec.json` and
produces reproducible PNG, SVG, and PDF outputs plus the exact `data_used.csv`.
