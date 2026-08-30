from figure_tools.validation.formal_text import formal_text_checks
from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox


def test_formal_text_checks_compare_labels_and_formulas_to_authoritative_map():
    plan = {
        "text_elements": [
            {"element_id": "label-a", "kind": "label", "content": "(a) Input"},
            {"element_id": "eq-1", "kind": "equation", "content": "E = mc^2"},
        ],
    }
    manifest = LayoutManifest(
        schema_version="1.0",
        artifact_id="assembly:figure",
        coordinate_system="pixel_top_left",
        canvas_width_px=1000,
        canvas_height_px=500,
        elements=[
            LayoutElement(
                element_id="label-a", element_type="panel_label",
                bbox=PixelBBox(10, 10, 100, 30), text="(a) Input",
                font_size_pt=8, source="assembly",
            ),
            LayoutElement(
                element_id="eq-1", element_type="equation",
                bbox=PixelBBox(10, 50, 150, 80), text="E = mc^3",
                font_size_pt=7, source="assembly",
            ),
        ],
    )

    checks = formal_text_checks(plan, manifest)
    by_id = {item["check_id"]: item for item in checks}

    assert by_id["formal_text_exact_match"]["status"] == "fail"
    assert by_id["formula_exact_match"]["status"] == "fail"
    assert by_id["formula_exact_match"]["element_ids"] == ["eq-1"]
