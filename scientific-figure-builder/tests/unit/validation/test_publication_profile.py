from __future__ import annotations

from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.publication import publication_profile_checks


def _manifest(font_size=7.0):
    return LayoutManifest(
        schema_version="1.0",
        artifact_id="assembly:figure",
        coordinate_system="pixel_top_left",
        canvas_width_px=2100,
        canvas_height_px=1200,
        elements=[LayoutElement(
            element_id="label",
            element_type="text",
            bbox=PixelBBox(10, 10, 100, 30),
            text="Receptor",
            font_size_pt=font_size,
            source="assembly",
        )],
    )


def test_nature_profile_checks_physical_size_and_final_typography():
    checks = publication_profile_checks(
        "nature_research", _manifest(), (89, 100), editable_svg_exists=True,
    )
    by_id = {item["check_id"]: item for item in checks}

    assert by_id["publication_dimensions"]["status"] == "pass"
    assert by_id["publication_typography"]["status"] == "pass"
    assert by_id["publication_editable_vectors"]["status"] == "pass"

    failing = publication_profile_checks(
        "nature_research", _manifest(font_size=9), (140, 180),
        editable_svg_exists=False,
    )
    failing_by_id = {item["check_id"]: item for item in failing}
    assert failing_by_id["publication_dimensions"]["status"] == "fail"
    assert failing_by_id["publication_typography"]["status"] == "fail"
    assert failing_by_id["publication_editable_vectors"]["status"] == "fail"
