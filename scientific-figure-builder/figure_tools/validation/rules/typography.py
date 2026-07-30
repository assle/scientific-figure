"""Typography rule: minimum font size (plan section 11.5)."""

from __future__ import annotations

from collections import defaultdict

from figure_tools.validation.models import LayoutManifest
from figure_tools.validation.rules.overlap import TEXT_TYPES
from figure_tools.validation.summary import make_check


def minimum_font_size(manifest: LayoutManifest, thresholds: dict) -> list[dict]:
    critical = float(thresholds.get("critical_font_size_pt", 6))
    minimum = float(thresholds.get("minimum_font_size_pt", 7))
    tol = float(thresholds.get("font_size_tolerance_pt", 1))
    checks: list[dict] = []

    by_type: dict[str, list[float]] = defaultdict(list)
    for e in manifest.elements:
        if e.element_type not in TEXT_TYPES or e.font_size_pt is None:
            continue
        size = float(e.font_size_pt)
        by_type[e.element_type].append(size)
        if size < critical:
            checks.append(make_check(
                "minimum_font_size", "final", "error", "fail",
                f"{e.element_id} font size {size:.1f} pt < critical {critical:.1f} pt",
                element_ids=[e.element_id], confidence=1.0, method="geometry",
                repair_action=f"increase {e.element_id} font size to >= {minimum:.0f} pt",
            ))
        elif size < minimum:
            checks.append(make_check(
                "minimum_font_size", "final", "warning", "fail",
                f"{e.element_id} font size {size:.1f} pt < minimum {minimum:.1f} pt",
                element_ids=[e.element_id], confidence=1.0, method="geometry",
                repair_action=f"increase {e.element_id} font size to >= {minimum:.0f} pt",
            ))

    # Same-type size consistency.
    for etype, sizes in by_type.items():
        if len(sizes) >= 2 and (max(sizes) - min(sizes)) > tol:
            checks.append(make_check(
                "minimum_font_size", "final", "warning", "fail",
                f"{etype} font sizes vary by {max(sizes) - min(sizes):.1f} pt "
                f"(tolerance {tol:.1f} pt)",
                confidence=1.0, method="geometry",
                repair_action=f"unify {etype} font sizes",
            ))

    if not checks:
        checks.append(make_check("minimum_font_size", "final", "warning", "pass",
                                 "font sizes within limits"))
    return checks


__all__ = ["minimum_font_size"]
