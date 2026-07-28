"""Deterministic image-asset checks (plan section 11)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from figure_tools.validation.image_checks import deterministic_image_checks


def _save(path: Path, mode, size=(1024, 1024), with_content=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "RGBA":
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        if with_content:
            ImageDraw.Draw(img).ellipse((384, 384, 640, 640), fill=(200, 40, 40, 255))
    else:
        img = Image.new(mode, size, (255, 255, 255))
    img.save(path)


def _by_id(checks):
    return {c["check_id"]: c for c in checks}


def test_rgba_image_passes_core_checks(tmp_path: Path):
    img = tmp_path / "a.png"
    _save(img, "RGBA")
    checks = _by_id(deterministic_image_checks(img, physical_size_mm=(80, 80)))
    assert checks["file_integrity"]["status"] == "pass"
    assert checks["alpha_channel"]["status"] == "pass"
    assert checks["blank_output"]["status"] == "pass"
    assert checks["effective_dpi"]["status"] == "pass"
    assert checks["edge_margins"]["status"] == "pass"


def test_rgb_image_fails_alpha(tmp_path: Path):
    img = tmp_path / "a.png"
    _save(img, "RGB")
    checks = _by_id(deterministic_image_checks(img))
    assert checks["alpha_channel"]["status"] == "fail"


def test_fully_transparent_is_blank(tmp_path: Path):
    img = tmp_path / "a.png"
    _save(img, "RGBA", with_content=False)
    checks = _by_id(deterministic_image_checks(img))
    assert checks["blank_output"]["status"] == "fail"


def test_low_effective_dpi_fails(tmp_path: Path):
    img = tmp_path / "a.png"
    _save(img, "RGBA", size=(64, 64))
    checks = _by_id(deterministic_image_checks(img, physical_size_mm=(80, 80)))
    assert checks["effective_dpi"]["status"] == "fail"


def test_corrupt_file_fails_integrity(tmp_path: Path):
    img = tmp_path / "a.png"
    img.write_bytes(b"not a png")
    checks = _by_id(deterministic_image_checks(img))
    assert checks["file_integrity"]["status"] == "fail"
