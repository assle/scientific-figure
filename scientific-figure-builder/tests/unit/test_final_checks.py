"""Final assembled-figure validation tests (plan section 11)."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from figure_tools.validation.final_checks import validate_assembled_figure

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


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
        "panels": [
            {"panel_id": "a", "bbox": [0, 0, 0.5, 1], "physical_size": [90, 112.5]},
            {"panel_id": "b", "bbox": [0.5, 0, 0.5, 1], "physical_size": [90, 112.5]},
        ],
        "assets": [
            {"asset_id": "curve", "type": "data_plot", "z_order": 1, "dependencies": [],
             "routing": "python"},
            {"asset_id": "fiber", "type": "image_asset", "z_order": 2, "dependencies": [],
             "routing": "ark_image"},
        ],
        "style_bible_ref": "default", "text_elements": [],
        "assumptions": [], "uncertainties": [], "user_input_requirements": [],
        "estimated_paid_calls": {"reference_analysis": 0, "generation": 1, "edits": 0,
                                 "validations": 1, "final_validation": 1},
        "planned_uploads": [], "approval": {"status": "approved"},
    }


def _manifest(curve_path, fiber_path, fiber_transparent=True):
    return {
        "schema_version": "1.0",
        "assets": [
            {"asset_id": "curve", "type": "data_plot", "path": str(curve_path),
             "content_hash": "sha256:c", "pixel_dimensions": [1024, 800],
             "transparent": False, "z_order": 1,
             "validation_result": {"status": "pass"}},
            {"asset_id": "fiber", "type": "image_asset", "path": str(fiber_path),
             "content_hash": "sha256:f", "pixel_dimensions": [2048, 1280],
             "transparent": fiber_transparent, "z_order": 2,
             "validation_result": {"status": "pass"}},
        ],
    }


def test_happy_path_not_blocking(tmp_path: Path):
    composed = tmp_path / "figure.png"
    _save_rgba(composed)
    curve = tmp_path / "curve.png"; _save_rgba(curve)
    fiber = tmp_path / "fiber.png"; _save_rgba(fiber)
    report = validate_assembled_figure(_plan(), _manifest(curve, fiber), composed,
                                       physical_size_mm=(180, 112.5))
    assert report["summary"]["errors"] == 0
    assert report["summary"]["blocking"] is False


def test_missing_asset_is_blocking(tmp_path: Path):
    composed = tmp_path / "figure.png"; _save_rgba(composed)
    curve = tmp_path / "missing.png"  # does not exist
    fiber = tmp_path / "fiber.png"; _save_rgba(fiber)
    report = validate_assembled_figure(_plan(), _manifest(curve, fiber), composed,
                                       physical_size_mm=(180, 112.5))
    assert report["summary"]["errors"] >= 1
    assert report["summary"]["blocking"] is True
    assert any(c["check_id"] == "missing_assets" and c["status"] == "fail"
               for c in report["checks"])


def test_ai_asset_missing_alpha_is_blocking(tmp_path: Path):
    composed = tmp_path / "figure.png"; _save_rgba(composed)
    curve = tmp_path / "curve.png"
    Image.new("RGB", (1024, 800), (255, 255, 255)).save(curve)
    fiber = tmp_path / "fiber.png"
    Image.new("RGB", (2048, 1280), (255, 255, 255)).save(fiber)  # no alpha
    report = validate_assembled_figure(_plan(), _manifest(curve, fiber,
                                                           fiber_transparent=False),
                                       composed, physical_size_mm=(180, 112.5))
    assert report["summary"]["blocking"] is True
    assert any(c["check_id"] == "alpha_for_ai_assets" and c["status"] == "fail"
               for c in report["checks"])


def test_low_resolution_is_warning_not_blocking(tmp_path: Path):
    composed = tmp_path / "figure.png"
    _save_rgba(composed, size=(64, 40))  # very low dpi at 180mm
    curve = tmp_path / "curve.png"; _save_rgba(curve)
    fiber = tmp_path / "fiber.png"; _save_rgba(fiber)
    report = validate_assembled_figure(_plan(), _manifest(curve, fiber), composed,
                                       physical_size_mm=(180, 112.5))
    assert report["summary"]["blocking"] is False
    assert report["summary"]["warnings"] >= 1
    assert any(c["check_id"] == "effective_resolution" and c["status"] == "fail"
               for c in report["checks"])


def test_report_conforms_to_schema(tmp_path: Path):
    composed = tmp_path / "figure.png"; _save_rgba(composed)
    curve = tmp_path / "curve.png"; _save_rgba(curve)
    fiber = tmp_path / "fiber.png"; _save_rgba(fiber)
    report = validate_assembled_figure(_plan(), _manifest(curve, fiber), composed,
                                       physical_size_mm=(180, 112.5))
    from jsonschema import Draft202012Validator
    from figure_tools._resources import schema_path
    schema = json.loads(schema_path("validation-report.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(report))
