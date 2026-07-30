"""Unit tests for evidence crop generation (plan section 20.1)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from figure_tools.validation.evidence import generate_evidence


def _make_image(path: Path, size=(400, 300)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", size, (255, 255, 255, 255))
    ImageDraw.Draw(img).rectangle((50, 50, 150, 120), fill=(0, 0, 0, 255))
    img.save(path)


def test_evidence_generated_for_failing_check_with_bbox(tmp_path: Path):
    img = tmp_path / "fig.png"
    _make_image(img)
    checks = [
        {"check_id": "text_text_overlap", "status": "fail", "level": "error",
         "bbox": [60, 60, 140, 110], "element_ids": ["a", "b"],
         "detail": "overlap"},
        {"check_id": "ok", "status": "pass", "level": "warning"},
    ]
    out = generate_evidence(img, checks, tmp_path / "evidence",
                            {"crop_padding_pixels": 10, "crop_scale": 2,
                             "draw_boxes": True})
    fail_check = next(c for c in out if c["check_id"] == "text_text_overlap")
    assert "evidence_path" in fail_check
    ev = Path(fail_check["evidence_path"])
    assert ev.exists()
    # The crop is scaled up.
    cropped = Image.open(ev)
    assert cropped.width > 80 and cropped.height > 50
    # Passing check gets no evidence path.
    assert "evidence_path" not in next(c for c in out if c["check_id"] == "ok")


def test_evidence_skips_check_without_bbox(tmp_path: Path):
    img = tmp_path / "fig.png"
    _make_image(img)
    checks = [{"check_id": "missing_assets", "status": "fail", "level": "error",
               "detail": "no bbox here"}]
    out = generate_evidence(img, checks, tmp_path / "evidence", {})
    assert "evidence_path" not in out[0]
    assert not (tmp_path / "evidence").exists() or not any(
        (tmp_path / "evidence").iterdir())


def test_evidence_clips_to_canvas_and_counts(tmp_path: Path):
    img = tmp_path / "fig.png"
    _make_image(img, size=(200, 200))
    checks = [
        {"check_id": "text_clipping", "status": "fail", "level": "error",
         "bbox": [-50, -50, 10, 10]},
        {"check_id": "text_clipping", "status": "fail", "level": "error",
         "bbox": [190, 190, 260, 260]},
    ]
    out = generate_evidence(img, checks, tmp_path / "evidence",
                            {"crop_padding_pixels": 5, "crop_scale": 1,
                             "draw_boxes": False})
    paths = [Path(c["evidence_path"]) for c in out if "evidence_path" in c]
    assert len(paths) == 2
    names = sorted(p.name for p in paths)
    assert names == ["text_clipping_001.png", "text_clipping_002.png"]
    for p in paths:
        assert p.exists()
