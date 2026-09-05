"""Top-level plot renderer: ties spec, data, recipes, and exporters together."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from figure_tools.export.exporters import save_figure
from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.recipes import render
from figure_tools.plotting.spec import PlotSpec
from figure_tools.vector.svg_normalize import resolve_export_target


def render_plot(
    spec: PlotSpec,
    output_dir: str | Path,
    base_dir: str | Path | None = None,
    basename: str = "plot",
    export_target: str | None = None,
) -> dict[str, dict[str, str]]:
    base = Path(base_dir) if base_dir else Path.cwd()
    src_path = base / spec.source_data["path"]
    source = load_source_data(src_path)
    data_used = build_data_used(spec, source)
    export_target = resolve_export_target(
        export_target or spec.export.get("export_target", "general")
    )

    fig = render(spec, data_used)
    try:
        # Source-level layout extraction (plan section 8): draw first so every
        # artist has a real pixel bounding box, then write the manifest.
        fig.canvas.draw()
        from figure_tools.validation.extractors.matplotlib import (
            extract_matplotlib_layout,
        )
        from figure_tools.validation.models import write_layout_manifest

        layout = extract_matplotlib_layout(fig=fig, artifact_id=f"plot:{basename}")
        out_dir = Path(output_dir)
        layout_path = write_layout_manifest(out_dir / "layout_manifest.json", layout)

        files = save_figure(
            fig,
            out_dir,
            basename=basename,
            formats=tuple(spec.export["formats"]),
            dpi=spec.export.get("dpi", 300),
            export_target=export_target,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        data_used_path = out_dir / "data_used.csv"
        data_used.to_csv(data_used_path, index=False)
        files["data_used.csv"] = data_used_path
        files["layout_manifest.json"] = layout_path
    finally:
        plt.close(fig)

    return {"files": {k: str(v) for k, v in files.items()}}
