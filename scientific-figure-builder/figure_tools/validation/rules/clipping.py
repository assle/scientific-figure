"""Text clipping and asset-bounds rules (plan sections 11.2, 11.7)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutManifest, PixelBBox
from figure_tools.validation.rules.geometry import contains
from figure_tools.validation.rules.overlap import TEXT_TYPES
from figure_tools.validation.summary import make_check


def _panels(manifest: LayoutManifest) -> dict[str, PixelBBox]:
    """Map panel_id -> PixelBBox. Prefer explicit ``panel`` elements (the
    allocated region) and fall back to ``data_region`` (the plotting box)."""
    panels: dict[str, PixelBBox] = {}
    fallback: dict[str, PixelBBox] = {}
    for e in manifest.elements:
        if e.element_type == "panel" and e.panel_id:
            panels[e.panel_id] = e.bbox
        elif e.element_type == "data_region" and e.panel_id:
            fallback[e.panel_id] = e.bbox
    for pid, bbox in fallback.items():
        panels.setdefault(pid, bbox)
    return panels


def text_clipping(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    pad = float(thresholds.get("panel_padding_pixels", 2))
    cw, ch = manifest.canvas_width_px, manifest.canvas_height_px
    panels = _panels(manifest)
    checks: list[dict] = []

    for e in manifest.elements:
        if e.element_type not in TEXT_TYPES:
            continue
        b = e.bbox
        # Canvas clipping: no text may leave the canvas (panel labels included).
        if b.x1 < 0 or b.y1 < 0 or b.x2 > cw or b.y2 > ch:
            checks.append(make_check(
                "text_clipping", "final", "error", "fail",
                f"{e.element_id} extends beyond the canvas",
                element_ids=[e.element_id], bbox=b.as_list(),
                confidence=1.0, method="geometry",
                repair_action=f"move {e.element_id} inside the canvas",
            ))
            continue

        # Panel clipping: text should stay within its panel (plus padding).
        # Panel labels are allowed to sit in the padding zone, so they are only
        # checked against the canvas above.
        if e.element_type == "panel_label":
            continue
        if e.panel_id and e.panel_id in panels:
            pb = panels[e.panel_id]
            if not contains(pb, b, padding=pad):
                checks.append(make_check(
                    "text_clipping", "final", "warning", "fail",
                    f"{e.element_id} extends beyond panel {e.panel_id}",
                    element_ids=[e.element_id], bbox=b.as_list(),
                    confidence=1.0, method="geometry",
                    repair_action=f"move {e.element_id} inside panel {e.panel_id}",
                ))

    if not checks:
        checks.append(make_check("text_clipping", "final", "warning", "pass",
                                 "no text clipping detected"))
    return checks


def asset_bounds(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    """Check that data regions, legends and colorbars stay within the canvas
    and within their panel (plan section 11.7)."""
    pad = float(thresholds.get("panel_padding_pixels", 2))
    cw, ch = manifest.canvas_width_px, manifest.canvas_height_px
    panels = _panels(manifest)
    bounded_types = {"image_asset", "data_region", "legend", "colorbar"}
    checks: list[dict] = []

    for e in manifest.elements:
        if e.element_type not in bounded_types:
            continue
        b = e.bbox
        if b.x1 < -pad or b.y1 < -pad or b.x2 > cw + pad or b.y2 > ch + pad:
            checks.append(make_check(
                "asset_bounds", "final", "error", "fail",
                f"{e.element_id} extends beyond the canvas",
                element_ids=[e.element_id], bbox=b.as_list(),
                confidence=1.0, method="geometry",
                repair_action=f"resize or reposition {e.element_id}",
            ))
            continue
        if e.panel_id and e.panel_id in panels:
            pb = panels[e.panel_id]
            if not contains(pb, b, padding=pad):
                checks.append(make_check(
                    "asset_bounds", "final", "warning", "fail",
                    f"{e.element_id} extends beyond panel {e.panel_id}",
                    element_ids=[e.element_id], bbox=b.as_list(),
                    confidence=1.0, method="geometry",
                    repair_action=f"keep {e.element_id} within panel {e.panel_id}",
                ))

    if not checks:
        checks.append(make_check("asset_bounds", "final", "warning", "pass",
                                 "all assets within bounds"))
    return checks


__all__ = ["text_clipping", "asset_bounds"]
