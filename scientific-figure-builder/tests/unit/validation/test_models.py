"""Unit tests for layout-manifest data models (plan section 6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.validation.models import (
    LayoutElement,
    LayoutManifest,
    PixelBBox,
    read_layout_manifest,
    write_layout_manifest,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures"


def _schema():
    return json.loads(schema_path("layout-manifest.schema.json").read_text(encoding="utf-8"))


def test_pixel_bbox_width_height_area():
    b = PixelBBox(10, 20, 30, 50)
    assert b.width == 20
    assert b.height == 30
    assert b.area == 600


def test_pixel_bbox_normalises_inverted_corners():
    b = PixelBBox(30, 50, 10, 20)
    assert (b.x1, b.y1, b.x2, b.y2) == (10, 20, 30, 50)
    assert b.area == 600


def test_pixel_bbox_zero_area():
    b = PixelBBox(5, 5, 5, 5)
    assert b.area == 0.0
    assert b.width == 0.0


def test_pixel_bbox_from_list_validates_length():
    with pytest.raises(ValueError):
        PixelBBox.from_list([1, 2, 3])


def test_layout_element_rejects_unknown_type():
    with pytest.raises(ValueError):
        LayoutElement(element_id="x", element_type="not_a_type", bbox=PixelBBox(0, 0, 1, 1))


def test_manifest_round_trip(tmp_path: Path):
    manifest = LayoutManifest(
        schema_version="1.0",
        artifact_id="plot:line",
        coordinate_system="pixel_top_left",
        canvas_width_px=1200,
        canvas_height_px=750,
        elements=[
            LayoutElement("title_0", "title", PixelBBox(430, 18, 770, 54),
                          panel_id="a", text="Coupling", font_size_pt=12.0, z_order=5,
                          source="matplotlib"),
            LayoutElement("ylabel_0", "axis_label", PixelBBox(18, 320, 90, 410),
                          panel_id="a", text="Efficiency (%)", font_size_pt=11.0,
                          rotation_deg=90.0, source="matplotlib"),
        ],
    )
    path = write_layout_manifest(tmp_path / "layout_manifest.json", manifest)
    loaded = read_layout_manifest(path)
    assert loaded.artifact_id == "plot:line"
    assert loaded.canvas_width_px == 1200
    assert loaded.elements[0].text == "Coupling"
    assert loaded.elements[1].rotation_deg == 90.0
    assert loaded.elements[1].bbox.as_list() == [18, 320, 90, 410]


def test_serialized_manifest_validates_against_schema():
    manifest = LayoutManifest(
        schema_version="1.0",
        artifact_id="assembly:figure",
        coordinate_system="pixel_top_left",
        canvas_width_px=2126,
        canvas_height_px=1063,
        elements=[
            LayoutElement("panel_a_label", "panel_label", PixelBBox(12, 18, 68, 132),
                          panel_id="a", text="(a)", font_size_pt=9.0, source="assembly"),
        ],
    )
    errors = list(Draft202012Validator(_schema()).iter_errors(manifest.to_dict()))
    assert not errors, "; ".join(e.message for e in errors)


def test_fixture_manifest_validates_and_loads():
    data = json.loads((FIXTURES / "layout_manifest.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(_schema()).iter_errors(data))
    manifest = LayoutManifest.from_dict(data)
    assert manifest.coordinate_system == "pixel_top_left"
    assert len(manifest.elements) == 3
    assert manifest.elements[0].element_type == "data_region"


def test_schema_rejects_bad_bbox_and_confidence():
    schema = _schema()
    bad_bbox = {
        "schema_version": "1.0", "artifact_id": "x",
        "coordinate_system": "pixel_top_left",
        "canvas": {"width_px": 100, "height_px": 100},
        "elements": [{"element_id": "e", "element_type": "text", "bbox": [1, 2, 3]}],
    }
    assert list(Draft202012Validator(schema).iter_errors(bad_bbox))
    bad_type = {
        "schema_version": "1.0", "artifact_id": "x",
        "coordinate_system": "pixel_top_left",
        "canvas": {"width_px": 100, "height_px": 100},
        "elements": [{"element_id": "e", "element_type": "bogus", "bbox": [1, 2, 3, 4]}],
    }
    assert list(Draft202012Validator(schema).iter_errors(bad_type))
