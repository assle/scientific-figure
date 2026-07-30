"""Figure compositor: assemble panel assets into a final figure (plan section 10).

The image model never generates the final compound figure; composition is
deterministic via matplotlib image placement. When source layout manifests are
available, the compositor also emits an assembly-level layout manifest that
projects every source element onto the final canvas (plan section 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.image import imread  # noqa: E402

from figure_tools.export.exporters import save_figure  # noqa: E402
from figure_tools.validation.extractors.assembly import (  # noqa: E402
    load_source_manifests,
    text_artist_element,
    transform_source_manifest,
)
from figure_tools.validation.models import (  # noqa: E402
    LayoutElement,
    LayoutManifest,
    PixelBBox,
    write_layout_manifest,
)


def compose_assets(
    placements: list[dict[str, Any]],
    output_dir: str | Path,
    canvas_mm: tuple[float, float],
    dpi: int = 300,
    text_placements: list[dict[str, Any]] | None = None,
    source_layouts: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
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

    # Track composed text artists so their real bboxes can be extracted after
    # the figure is drawn (plan section 9.3).
    text_artists: list[tuple[dict[str, Any], Any]] = []
    for t in text_placements or []:
        x = t["x"]
        y = 1 - t["y"]  # top-origin -> bottom-origin
        artist = ax.text(x, y, t["text"], fontsize=t.get("font_size", 9),
                         ha="left", va="top", zorder=100, clip_on=False)
        text_artists.append((t, artist))

    canvas_w, canvas_h = fig.canvas.get_width_height()
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
    except Exception:  # noqa: BLE001
        renderer = None

    elements: list[LayoutElement] = []

    # Record each panel's allocated region on the final canvas (plan section 9).
    for p in placements:
        if not p.get("asset_id"):
            continue
        px, py, pw, ph = p["bbox"]
        elements.append(LayoutElement(
            element_id=f"panel:{p['asset_id']}",
            element_type="panel",
            bbox=PixelBBox(px * canvas_w, py * canvas_h,
                           (px + pw) * canvas_w, (py + ph) * canvas_h),
            panel_id=p.get("panel_id"),
            source="assembly",
            z_order=int(p.get("z_order", 0)),
        ))

    # Project source layout elements onto the final canvas.
    source_manifests = load_source_manifests(source_layouts)
    placement_by_id = {p.get("asset_id"): p for p in placements if p.get("asset_id")}
    for asset_id, manifest in source_manifests.items():
        placement = placement_by_id.get(asset_id)
        if placement is None:
            continue
        panel_id = placement.get("panel_id")
        elements.extend(transform_source_manifest(
            manifest, placement, int(canvas_w), int(canvas_h), panel_id))

    # Composed text (panel labels etc.).
    for t, artist in text_artists:
        element_id = t.get("element_id") or f"text_{len(elements)}"
        kind = t.get("kind", "text")
        element_type = "panel_label" if kind == "label" else "text"
        el = text_artist_element(artist, int(canvas_h), element_id,
                                 t.get("panel_id"), element_type, renderer)
        if el is not None:
            elements.append(el)

    manifest = LayoutManifest(
        schema_version="1.0",
        artifact_id="assembly:figure",
        coordinate_system="pixel_top_left",
        canvas_width_px=int(canvas_w),
        canvas_height_px=int(canvas_h),
        elements=elements,
    )

    try:
        files = save_figure(fig, output_dir, basename="figure",
                            formats=("png", "svg", "pdf"), dpi=dpi)
    finally:
        plt.close(fig)

    layout_path = write_layout_manifest(Path(output_dir) / "layout_manifest.json", manifest)

    return {
        "files": {k: str(v) for k, v in files.items()},
        "layout_manifest": str(layout_path),
    }
