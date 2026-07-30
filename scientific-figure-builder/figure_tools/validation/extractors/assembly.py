"""Assembly layout extraction (plan section 9).

Maps source-level layout elements from each placed asset into the final
composed-canvas coordinate system, and records composed text (panel labels)
drawn by the compositor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from figure_tools.validation.models import (
    LayoutElement,
    LayoutManifest,
    LayoutManifest as _Manifest,
    PixelBBox,
    read_layout_manifest,
)


def map_bbox(
    bbox: PixelBBox,
    placement_bbox: list[float],
    canvas_w: int,
    canvas_h: int,
    source_w: int,
    source_h: int,
) -> PixelBBox:
    """Map a source-canvas bbox into the final composed canvas (plan 9.2).

    ``placement_bbox`` is the normalized ``[px, py, pw, ph]`` rectangle
    (top-left origin) where the source image is placed on the canvas.
    """
    px, py, pw, ph = placement_bbox
    scale_x = pw * canvas_w / source_w
    scale_y = ph * canvas_h / source_h
    return PixelBBox(
        px * canvas_w + bbox.x1 * scale_x,
        py * canvas_h + bbox.y1 * scale_y,
        px * canvas_w + bbox.x2 * scale_x,
        py * canvas_h + bbox.y2 * scale_y,
    )


def transform_source_manifest(
    source_manifest: LayoutManifest,
    placement: dict[str, Any],
    canvas_w: int,
    canvas_h: int,
    panel_id: str | None = None,
) -> list[LayoutElement]:
    """Project every element of a source manifest onto the final canvas."""
    asset_id = placement.get("asset_id", "asset")
    sw = source_manifest.canvas_width_px
    sh = source_manifest.canvas_height_px
    z_order = int(placement.get("z_order", 0))
    out: list[LayoutElement] = []
    for el in source_manifest.elements:
        mapped = map_bbox(el.bbox, placement["bbox"], canvas_w, canvas_h, sw, sh)
        out.append(LayoutElement(
            element_id=f"{asset_id}:{el.element_id}",
            element_type=el.element_type,
            bbox=mapped,
            panel_id=panel_id if panel_id is not None else el.panel_id,
            text=el.text,
            font_size_pt=el.font_size_pt,
            rotation_deg=el.rotation_deg,
            z_order=z_order,
            source="assembly",
            metadata=dict(el.metadata),
        ))
    return out


def load_source_manifests(
    source_layouts: dict[str, str | Path] | None,
) -> dict[str, LayoutManifest]:
    if not source_layouts:
        return {}
    loaded: dict[str, LayoutManifest] = {}
    for asset_id, path in source_layouts.items():
        p = Path(path)
        if not p.exists():
            continue
        try:
            loaded[asset_id] = read_layout_manifest(p)
        except Exception:  # noqa: BLE001
            continue
    return loaded


def text_artist_element(
    artist,
    canvas_h: int,
    element_id: str,
    panel_id: str | None,
    element_type: str,
    renderer=None,
) -> LayoutElement | None:
    """Build a LayoutElement from a composed matplotlib text artist."""
    try:
        if not artist.get_text():
            return None
        if renderer is None:
            bbox = artist.get_window_extent()
        else:
            bbox = artist.get_window_extent(renderer=renderer)
    except Exception:  # noqa: BLE001
        return None
    x1, x2 = float(bbox.x0), float(bbox.x1)
    y1 = canvas_h - float(bbox.y1)
    y2 = canvas_h - float(bbox.y0)
    pb = PixelBBox(x1, y1, x2, y2)
    if pb.area <= 0.0:
        return None
    try:
        font_size = float(artist.get_fontsize())
    except Exception:  # noqa: BLE001
        font_size = None
    return LayoutElement(
        element_id=element_id,
        element_type=element_type,  # type: ignore[arg-type]
        bbox=pb,
        panel_id=panel_id,
        text=artist.get_text(),
        font_size_pt=font_size,
        rotation_deg=0.0,
        z_order=int(getattr(artist, "get_zorder", lambda: 100)()),
        source="assembly",
    )


__all__ = [
    "map_bbox",
    "transform_source_manifest",
    "load_source_manifests",
    "text_artist_element",
]
