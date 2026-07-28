"""Figure compositor: assemble panel assets into a final figure (plan section 10).

The image model never generates the final compound figure; composition is
deterministic via matplotlib image placement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.image import imread  # noqa: E402

from figure_tools.export.exporters import save_figure  # noqa: E402


def compose_assets(
    placements: list[dict[str, Any]],
    output_dir: str | Path,
    canvas_mm: tuple[float, float],
    dpi: int = 300,
    text_placements: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, str]]:
    w_mm, h_mm = canvas_mm
    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    for p in sorted(placements, key=lambda item: item.get("z_order", 0)):
        img = imread(p["path"])
        x, y, bw, bh = p["bbox"]
        # Plan bbox y origin is top; matplotlib extent y origin is bottom.
        extent = [x, x + bw, 1 - (y + bh), 1 - y]
        ax.imshow(img, extent=extent, aspect="auto",
                  zorder=p.get("z_order", 0), interpolation="nearest")

    for t in text_placements or []:
        x = t["x"]
        y = 1 - t["y"]  # top-origin -> bottom-origin
        ax.text(x, y, t["text"], fontsize=t.get("font_size", 9),
                ha="left", va="top", zorder=100, clip_on=False)

    try:
        files = save_figure(fig, output_dir, basename="figure",
                            formats=("png", "svg", "pdf"), dpi=dpi)
    finally:
        plt.close(fig)
    return {"files": {k: str(v) for k, v in files.items()}}
