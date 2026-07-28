# Plot recipes

Plot recipes are implemented in Phase 2 (deterministic local engines).

Expected v1 recipes (plan section 15, Phase 2):
- `line`
- `scatter`
- `bar`
- `heatmap`
- `error_bar`
- `multipanel`

Each recipe is a fixed, tested renderer that consumes a `plot_spec.json` and
produces reproducible PNG, SVG, and PDF outputs plus the exact `data_used.csv`.
