"""Geometry helpers for layout rules (plan section 11.1)."""

from __future__ import annotations

from figure_tools.validation.models import PixelBBox


def intersection_bbox(a: PixelBBox, b: PixelBBox) -> PixelBBox | None:
    """Axis-aligned intersection of two boxes. None if they do not overlap."""
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return PixelBBox(x1, y1, x2, y2)


def intersection_area(a: PixelBBox, b: PixelBBox) -> float:
    ib = intersection_bbox(a, b)
    return ib.area if ib is not None else 0.0


def contains(outer: PixelBBox, inner: PixelBBox, padding: float = 0.0) -> bool:
    """True if ``inner`` lies within ``outer`` expanded by ``padding``."""
    return (
        inner.x1 >= outer.x1 - padding
        and inner.y1 >= outer.y1 - padding
        and inner.x2 <= outer.x2 + padding
        and inner.y2 <= outer.y2 + padding
    )


__all__ = ["intersection_bbox", "intersection_area", "contains"]
