"""Top-level plot renderer: ties spec, data, recipes, and exporters together."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from figure_tools.export.exporters import save_figure
from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.recipes import render
from figure_tools.plotting.spec import PlotSpec


def render_plot(
    spec: PlotSpec,
    output_dir: str | Path,
    base_dir: str | Path | None = None,
    basename: str = "plot",
) -> dict[str, dict[str, str]]:
    base = Path(base_dir) if base_dir else Path.cwd()
    src_path = base / spec.source_data["path"]
    source = load_source_data(src_path)
    data_used = build_data_used(spec, source)

    fig = render(spec, data_used)
    try:
        files = save_figure(
            fig,
            output_dir,
            basename=basename,
            formats=tuple(spec.export["formats"]),
            dpi=spec.export.get("dpi", 300),
        )
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        data_used_path = out_dir / "data_used.csv"
        data_used.to_csv(data_used_path, index=False)
        files["data_used.csv"] = data_used_path
    finally:
        plt.close(fig)

    return {"files": {k: str(v) for k, v in files.items()}}
