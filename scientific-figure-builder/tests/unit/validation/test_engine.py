"""Unit tests for FigureQAEngine (plan section 20.3)."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from figure_tools.validation.engine import FigureQAEngine
from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox, write_layout_manifest


def _save_rgba(path: Path, size=(2048, 1280)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((400, 400, 1600, 880), fill=(200, 40, 40, 255))
    img.save(path)


def _plan():
    return {
        "schema_version": "1.0", "figure_id": "f1", "run_id": "f1",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": [{"panel_id": "a", "bbox": [0, 0, 1, 1], "physical_size": [180, 112.5]}],
        "assets": [{"asset_id": "curve", "type": "data_plot", "z_order": 1,
                    "dependencies": [], "routing": "python"}],
        "style_bible_ref": "default", "text_elements": [],
        "assumptions": [], "uncertainties": [], "user_input_requirements": [],
        "estimated_paid_calls": {}, "planned_uploads": [],
        "approval": {"status": "approved"},
    }


def _manifest(path=None, elements=None):
    m = LayoutManifest("1.0", "assembly:figure", "pixel_top_left", 1000, 1000,
                       elements or [])
    if path:
        return write_layout_manifest(path, m)
    return m


def _asset_manifest(curve_path):
    return {"schema_version": "1.0", "assets": [
        {"asset_id": "curve", "type": "data_plot", "path": str(curve_path),
         "content_hash": "sha256:c", "pixel_dimensions": [1024, 800],
         "transparent": False, "z_order": 1,
         "validation_result": {"status": "pass"}},
    ]}


def test_engine_runs_layout_rules_when_manifest_present(tmp_path: Path):
    composed = tmp_path / "figure.png"; _save_rgba(composed)
    curve = tmp_path / "curve.png"; _save_rgba(curve)
    # Two overlapping text elements -> text_text_overlap error.
    elements = [
        LayoutElement("panel_a", "panel", PixelBBox(0, 0, 1000, 1000), panel_id="a"),
        LayoutElement("a", "text", PixelBBox(10, 10, 200, 60), panel_id="a"),
        LayoutElement("b", "text", PixelBBox(20, 20, 210, 70), panel_id="a"),
    ]
    man_path = _manifest(tmp_path / "layout_manifest.json", elements)
    engine = FigureQAEngine(config={"thresholds": {"overlap_error_ratio": 0.03}})
    report = engine.validate_final(_plan(), _asset_manifest(curve), composed, man_path,
                                   (180, 112.5), run_id="r1")
    ids = {c["check_id"] for c in report["checks"]}
    assert "text_text_overlap" in ids
    overlap = [c for c in report["checks"]
               if c["check_id"] == "text_text_overlap" and c["status"] == "fail"]
    assert overlap and overlap[0]["level"] == "error"
    assert report["summary"]["blocking"] is True


def test_engine_falls_back_without_manifest(tmp_path: Path):
    composed = tmp_path / "figure.png"; _save_rgba(composed)
    curve = tmp_path / "curve.png"; _save_rgba(curve)
    engine = FigureQAEngine(config={})
    report = engine.validate_final(_plan(), _asset_manifest(curve), composed, None,
                                   (180, 112.5), run_id="r1")
    ids = {c["check_id"] for c in report["checks"]}
    # No geometry rules run; legacy panel-label consistency is used.
    assert "text_text_overlap" not in ids
    assert "panel_label_consistency" in ids
    assert report["summary"]["blocking"] is False


def test_engine_report_conforms_to_schema(tmp_path: Path):
    from jsonschema import Draft202012Validator
    from figure_tools._resources import schema_path
    composed = tmp_path / "figure.png"; _save_rgba(composed)
    curve = tmp_path / "curve.png"; _save_rgba(curve)
    man_path = _manifest(tmp_path / "layout_manifest.json", [
        LayoutElement("panel_a", "panel", PixelBBox(0, 0, 1000, 1000), panel_id="a"),
        LayoutElement("lab", "panel_label", PixelBBox(10, 10, 60, 50),
                      panel_id="a", text="(a)", font_size_pt=9.0),
    ])
    engine = FigureQAEngine(config={})
    report = engine.validate_final(_plan(), _asset_manifest(curve), composed, man_path,
                                   (180, 112.5), run_id="r1")
    schema = json.loads(schema_path("validation-report.schema.json").read_text("utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(report))
