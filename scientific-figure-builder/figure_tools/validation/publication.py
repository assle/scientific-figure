"""Deterministic checks for built-in Publication profiles."""

from __future__ import annotations

from figure_tools.publication_profiles import get_publication_profile
from figure_tools.validation.models import LayoutManifest
from figure_tools.validation.summary import make_check


def publication_profile_checks(
    profile_id: str,
    manifest: LayoutManifest | None,
    physical_size_mm: tuple[float, float],
    *,
    editable_svg_exists: bool,
) -> list[dict]:
    if profile_id == "general":
        return [make_check(
            "publication_profile",
            "final",
            "warning",
            "skipped",
            "general Publication profile has no journal-specific constraints",
        )]
    profile = get_publication_profile(profile_id)
    width, height = physical_size_mm
    allowed_widths = [float(value) for value in profile.get("widths_mm", [])]
    width_ok = not allowed_widths or any(
        abs(width - allowed) <= 0.5 for allowed in allowed_widths
    )
    maximum_height = float(profile.get("maximum_height_mm", height))
    dimensions_ok = width_ok and height <= maximum_height
    checks = [make_check(
        "publication_dimensions",
        "final",
        "error",
        "pass" if dimensions_ok else "fail",
        (
            f"{width:g}x{height:g} mm matches {profile_id}"
            if dimensions_ok
            else f"{profile_id} requires widths {allowed_widths} mm and "
                 f"height <= {maximum_height:g} mm"
        ),
    )]
    typography_errors = []
    if manifest is not None:
        ordinary_min, ordinary_max = (
            float(value) for value in profile.get("ordinary_text_pt", [0, 1000])
        )
        panel_label_size = float(profile.get("panel_label_pt", ordinary_max))
        for element in manifest.elements:
            if not element.text or element.font_size_pt is None:
                continue
            size = float(element.font_size_pt)
            if element.element_type == "panel_label":
                if abs(size - panel_label_size) > 0.25:
                    typography_errors.append(element.element_id)
            elif not ordinary_min <= size <= ordinary_max:
                typography_errors.append(element.element_id)
    checks.append(make_check(
        "publication_typography",
        "final",
        "error",
        "fail" if typography_errors else "pass",
        (
            "text outside Publication profile size limits: "
            + ", ".join(typography_errors)
            if typography_errors
            else "final text sizes satisfy the Publication profile"
        ),
        element_ids=typography_errors,
    ))
    checks.append(make_check(
        "publication_editable_vectors",
        "final",
        "error",
        "pass" if editable_svg_exists else "fail",
        (
            "editable SVG is present"
            if editable_svg_exists
            else "editable SVG is missing"
        ),
    ))
    return checks


__all__ = ["publication_profile_checks"]
