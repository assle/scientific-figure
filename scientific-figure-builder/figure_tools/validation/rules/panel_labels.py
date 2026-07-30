"""Panel-label rules (plan sections 11.3, 11.4)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.rules.geometry import intersection_bbox
from figure_tools.validation.summary import make_check

_PANEL_LABEL_RE = re.compile(r"^\s*\(\s*[a-zA-Z]+\s*\)")
_COLLISION_TYPES = {"title", "axis_label", "tick_label", "colorbar", "text"}


def _panel_label_elements(manifest: LayoutManifest) -> list[LayoutElement]:
    return [e for e in manifest.elements if e.element_type == "panel_label"]


def panel_label_collision(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    min_overlap_px = float(thresholds.get("minimum_overlap_pixels", 2))
    labels = _panel_label_elements(manifest)
    checks: list[dict] = []

    for label in labels:
        for other in manifest.elements:
            if other.element_id == label.element_id:
                continue
            if other.element_type not in _COLLISION_TYPES:
                continue
            ib = intersection_bbox(label.bbox, other.bbox)
            if ib is None or ib.width < min_overlap_px or ib.height < min_overlap_px:
                continue
            checks.append(make_check(
                "panel_label_collision", "final", "error", "fail",
                f"panel label {label.element_id} overlaps {other.element_id}",
                element_ids=[label.element_id, other.element_id],
                bbox=ib.as_list(), confidence=1.0, method="geometry",
                repair_action=f"move {label.element_id} away from {other.element_id}",
            ))

    if not checks:
        checks.append(make_check("panel_label_collision", "final", "error", "pass",
                                 "no panel-label collisions"))
    return checks


def panel_label_consistency(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    labels = _panel_label_elements(manifest)
    panels = [e for e in manifest.elements if e.element_type == "panel"
              and e.panel_id]
    if not panels:
        panels = [e for e in manifest.elements if e.element_type == "data_region"
                  and e.panel_id]
    panel_ids = [e.panel_id for e in panels]
    panel_boxes = {e.panel_id: e.bbox for e in panels}
    checks: list[dict] = []
    tol = float(thresholds.get("font_size_tolerance_pt", 1))

    # One label per panel.
    by_panel: dict[str | None, list[LayoutElement]] = defaultdict(list)
    for lab in labels:
        by_panel[lab.panel_id].append(lab)
    for pid in panel_ids:
        n = len(by_panel.get(pid, []))
        if n == 0:
            checks.append(make_check("panel_label_consistency", "final", "warning",
                                "fail", f"panel {pid} has no panel label"))
        elif n > 1:
            checks.append(make_check("panel_label_consistency", "final", "warning",
                                "fail", f"panel {pid} has {n} panel labels"))

    # Duplicate label text.
    text_counts = Counter(lab.text for lab in labels if lab.text)
    for text, count in text_counts.items():
        if count > 1:
            checks.append(make_check("panel_label_consistency", "final", "warning",
                                "fail", f"duplicate panel label {text!r}"))

    # Format and top-left placement.
    for lab in labels:
        if lab.text and not _PANEL_LABEL_RE.match(lab.text):
            checks.append(make_check("panel_label_consistency", "final", "warning",
                                "fail",
                                f"panel label {lab.element_id} text {lab.text!r} "
                                "is not in (a) format"))
        if lab.panel_id and lab.panel_id in panel_boxes:
            pb: PixelBBox = panel_boxes[lab.panel_id]
            # Label should be in the top-left quadrant of its panel.
            mid_x = pb.x1 + pb.width / 2
            mid_y = pb.y1 + pb.height / 2
            if lab.bbox.x1 >= mid_x or lab.bbox.y1 >= mid_y:
                checks.append(make_check("panel_label_consistency", "final", "warning",
                                    "fail",
                                    f"panel label {lab.element_id} is not in the "
                                    f"top-left of panel {lab.panel_id}"))

    # Consistent font size.
    sizes = [lab.font_size_pt for lab in labels if lab.font_size_pt is not None]
    if len(sizes) >= 2 and (max(sizes) - min(sizes)) > tol:
        checks.append(make_check("panel_label_consistency", "final", "warning", "fail",
                            f"panel label font sizes vary by "
                            f"{max(sizes) - min(sizes):.1f} pt"))

    if not checks:
        checks.append(make_check("panel_label_consistency", "final", "warning", "pass",
                                 "panel labels consistent"))
    return checks


__all__ = ["panel_label_collision", "panel_label_consistency"]
