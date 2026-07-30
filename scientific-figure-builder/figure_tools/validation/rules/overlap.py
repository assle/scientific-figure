"""Text-text overlap rule (plan section 11.1)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutManifest
from figure_tools.validation.rules.geometry import intersection_bbox
from figure_tools.validation.summary import make_check

TEXT_TYPES = frozenset(
    {"text", "panel_label", "axis_label", "tick_label", "title", "equation"}
)


def text_text_overlap(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    min_overlap_px = float(thresholds.get("minimum_overlap_pixels", 2))
    warn_ratio = float(thresholds.get("overlap_warning_ratio", 0.01))
    err_ratio = float(thresholds.get("overlap_error_ratio", 0.03))

    text_els = [e for e in manifest.elements if e.element_type in TEXT_TYPES]
    checks: list[dict] = []

    for i, a in enumerate(text_els):
        for b in text_els[i + 1:]:
            if a.element_id == b.element_id:
                continue
            # Panel-label collisions are handled by the dedicated rule.
            if "panel_label" in (a.element_type, b.element_type):
                continue
            if a.metadata.get("allow_overlap") or b.metadata.get("allow_overlap"):
                continue
            ib = intersection_bbox(a.bbox, b.bbox)
            if ib is None:
                continue
            if ib.width < min_overlap_px or ib.height < min_overlap_px:
                continue
            min_area = min(a.bbox.area, b.bbox.area)
            if min_area <= 0.0:
                continue
            ratio = ib.area / min_area
            if ratio < warn_ratio:
                continue

            level = "error" if ratio > err_ratio else "warning"

            checks.append(make_check(
                "text_text_overlap", "final", level, "fail",
                f"{a.element_id} overlaps {b.element_id} "
                f"({ratio * 100:.1f}% of smaller box)",
                element_ids=[a.element_id, b.element_id],
                bbox=ib.as_list(),
                confidence=1.0,
                method="geometry",
                repair_action=(
                    f"separate {a.element_id} and {b.element_id} by at least "
                    f"{min_overlap_px:.0f} px"
                ),
            ))

    if not checks:
        checks.append(make_check("text_text_overlap", "final", "warning", "pass",
                                 "no text elements overlap"))
    return checks


__all__ = ["text_text_overlap", "TEXT_TYPES"]
