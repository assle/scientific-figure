"""Colorbar collision rule (plan section 11.6)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutManifest
from figure_tools.validation.rules.geometry import contains, intersection_bbox
from figure_tools.validation.summary import make_check

_COLLISION_TYPES = {"axis_label", "title", "panel_label", "tick_label"}


def colorbar_collision(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    pad = float(thresholds.get("panel_padding_pixels", 2))
    min_overlap_px = float(thresholds.get("minimum_overlap_pixels", 2))
    colorbars = [e for e in manifest.elements if e.element_type == "colorbar"]
    if not colorbars:
        return [make_check("colorbar_collision", "final", "warning", "skipped",
                           "no colorbars present")]

    panels = {e.panel_id: e.bbox for e in manifest.elements
              if e.element_type == "data_region" and e.panel_id}
    checks: list[dict] = []

    for cb in colorbars:
        # Panel containment.
        if cb.panel_id and cb.panel_id in panels:
            if not contains(panels[cb.panel_id], cb.bbox, padding=pad):
                checks.append(make_check(
                    "colorbar_collision", "final", "warning", "fail",
                    f"colorbar {cb.element_id} extends beyond panel {cb.panel_id}",
                    element_ids=[cb.element_id], bbox=cb.bbox.as_list(),
                    confidence=1.0, method="geometry",
                    repair_action=f"keep {cb.element_id} within panel {cb.panel_id}",
                ))
        # Overlap with labels/title.
        for other in manifest.elements:
            if other.element_id == cb.element_id:
                continue
            if other.element_type not in _COLLISION_TYPES:
                continue
            ib = intersection_bbox(cb.bbox, other.bbox)
            if ib is None or ib.width < min_overlap_px or ib.height < min_overlap_px:
                continue
            checks.append(make_check(
                "colorbar_collision", "final", "error", "fail",
                f"colorbar {cb.element_id} overlaps {other.element_id}",
                element_ids=[cb.element_id, other.element_id],
                bbox=ib.as_list(), confidence=1.0, method="geometry",
                repair_action=f"move {cb.element_id} away from {other.element_id}",
            ))

    # Adjacent colorbars overlapping each other.
    for i, a in enumerate(colorbars):
        for b in colorbars[i + 1:]:
            ib = intersection_bbox(a.bbox, b.bbox)
            if ib is None or ib.width < min_overlap_px or ib.height < min_overlap_px:
                continue
            checks.append(make_check(
                "colorbar_collision", "final", "error", "fail",
                f"colorbars {a.element_id} and {b.element_id} overlap",
                element_ids=[a.element_id, b.element_id],
                bbox=ib.as_list(), confidence=1.0, method="geometry",
                repair_action=f"separate colorbars {a.element_id} and {b.element_id}",
            ))

    if not checks:
        checks.append(make_check("colorbar_collision", "final", "warning", "pass",
                                 "no colorbar collisions"))
    return checks


__all__ = ["colorbar_collision"]
