"""Matplotlib figure layout extraction (plan section 8).

Extracts real element bounding boxes from a drawn matplotlib Figure and
converts them to the top-left pixel convention used by the layout manifest.
Element classification relies on object identity (not string guessing).
"""

from __future__ import annotations

from typing import Any

from figure_tools.validation.models import (
    LayoutElement,
    LayoutManifest,
    PixelBBox,
)

_TEXT_ELEMENT_TYPES = {"text", "panel_label", "axis_label", "tick_label",
                       "title", "equation"}


def _canvas_size(fig) -> tuple[int, int]:
    w, h = fig.canvas.get_width_height()
    return int(w), int(h)


def _renderer(fig):
    try:
        return fig.canvas.get_renderer()
    except Exception:  # noqa: BLE001
        fig.canvas.draw()
        return fig.canvas.get_renderer()


def _to_top_left(bbox, canvas_height: float) -> PixelBBox:
    """Convert a matplotlib display Bbox (bottom-left origin) to top-left."""
    x1, x2 = float(bbox.x0), float(bbox.x1)
    y1 = canvas_height - float(bbox.y1)  # display top -> top-left y
    y2 = canvas_height - float(bbox.y0)  # display bottom -> top-left y
    return PixelBBox(x1, y1, x2, y2)


def _font_size_pt(artist) -> float | None:
    try:
        return float(artist.get_fontsize())
    except Exception:  # noqa: BLE001
        return None


def _rotation(artist) -> float:
    try:
        return float(artist.get_rotation()) % 360.0
    except Exception:  # noqa: BLE001
        return 0.0


def _zorder(artist) -> int:
    try:
        return int(artist.get_zorder())
    except Exception:  # noqa: BLE001
        return 0


def _text_bbox(artist, renderer, canvas_height: float) -> PixelBBox | None:
    try:
        if not artist.get_text():
            return None
        bbox = artist.get_window_extent(renderer=renderer)
    except Exception:  # noqa: BLE001
        return None
    pb = _to_top_left(bbox, canvas_height)
    if pb.area <= 0.0:
        return None
    return pb


def _element_from_text(
    element_id: str, element_type: str, artist, renderer, canvas_height: float,
    panel_id: str | None,
) -> LayoutElement | None:
    bbox = _text_bbox(artist, renderer, canvas_height)
    if bbox is None:
        return None
    return LayoutElement(
        element_id=element_id,
        element_type=element_type,  # type: ignore[arg-type]
        bbox=bbox,
        panel_id=panel_id,
        text=artist.get_text(),
        font_size_pt=_font_size_pt(artist),
        rotation_deg=_rotation(artist),
        z_order=_zorder(artist),
        source="matplotlib",
    )


def _colorbar_axes(fig) -> dict[int, Any]:
    """Map id(colorbar_axes) -> Colorbar for axes that host a colorbar."""
    found: dict[int, Any] = {}
    for ax in fig.axes:
        for image in getattr(ax, "images", []):
            cb = getattr(image, "colorbar", None)
            if cb is not None and getattr(cb, "ax", None) is not None:
                found[id(cb.ax)] = cb
    return found


def extract_matplotlib_layout(fig, artifact_id: str) -> LayoutManifest:
    """Extract a LayoutManifest from a drawn matplotlib Figure."""
    fig.canvas.draw()
    renderer = _renderer(fig)
    canvas_w, canvas_h = _canvas_size(fig)
    elements: list[LayoutElement] = []
    colorbar_axes = _colorbar_axes(fig)

    for ax_idx, ax in enumerate(fig.axes):
        is_colorbar = id(ax) in colorbar_axes

        # Data region (the axes position box).
        try:
            region_bbox = _to_top_left(ax.get_window_extent(renderer), canvas_h)
            elements.append(LayoutElement(
                element_id=f"axes_{ax_idx}",
                element_type="colorbar" if is_colorbar else "data_region",
                bbox=region_bbox,
                panel_id=None,
                source="matplotlib",
                z_order=_zorder(ax),
            ))
        except Exception:  # noqa: BLE001
            pass

        # Title.
        el = _element_from_text(f"title_{ax_idx}", "title", ax.title,
                                renderer, canvas_h, None)
        if el is not None:
            elements.append(el)

        # Axis labels.
        el = _element_from_text(f"xlabel_{ax_idx}", "axis_label",
                                ax.xaxis.label, renderer, canvas_h, None)
        if el is not None:
            elements.append(el)
        el = _element_from_text(f"ylabel_{ax_idx}", "axis_label",
                                ax.yaxis.label, renderer, canvas_h, None)
        if el is not None:
            elements.append(el)

        # Tick labels.
        for i, label in enumerate(ax.get_xticklabels()):
            el = _element_from_text(f"xtick_{ax_idx}_{i}", "tick_label",
                                    label, renderer, canvas_h, None)
            if el is not None:
                elements.append(el)
        for i, label in enumerate(ax.get_yticklabels()):
            el = _element_from_text(f"ytick_{ax_idx}_{i}", "tick_label",
                                    label, renderer, canvas_h, None)
            if el is not None:
                elements.append(el)

        # Legend.
        legend = ax.get_legend()
        if legend is not None:
            try:
                lbbox = legend.get_window_extent(renderer=renderer)
                pb = _to_top_left(lbbox, canvas_h)
                if pb.area > 0.0:
                    elements.append(LayoutElement(
                        element_id=f"legend_{ax_idx}",
                        element_type="legend",
                        bbox=pb,
                        panel_id=None,
                        text=legend.get_title().get_text() if legend.get_title() else None,
                        source="matplotlib",
                        z_order=_zorder(legend),
                    ))
            except Exception:  # noqa: BLE001
                pass

        # Other axes-level Text (not title/label/tick).
        known = {id(ax.title), id(ax.xaxis.label), id(ax.yaxis.label)}
        known.update(id(t) for t in ax.get_xticklabels())
        known.update(id(t) for t in ax.get_yticklabels())
        text_i = 0
        for artist in ax.texts:
            if id(artist) in known:
                continue
            el = _element_from_text(f"text_{ax_idx}_{text_i}", "text",
                                    artist, renderer, canvas_h, None)
            if el is not None:
                elements.append(el)
                text_i += 1

    # Figure-level text (e.g. fig.text(...) annotations).
    for i, artist in enumerate(getattr(fig, "texts", [])):
        el = _element_from_text(f"text_fig_{i}", "text", artist,
                                renderer, canvas_h, None)
        if el is not None:
            elements.append(el)

    return LayoutManifest(
        schema_version="1.0",
        artifact_id=artifact_id,
        coordinate_system="pixel_top_left",
        canvas_width_px=canvas_w,
        canvas_height_px=canvas_h,
        elements=elements,
    )


__all__ = ["extract_matplotlib_layout"]
