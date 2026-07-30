"""Unit tests for OCR fallback and unexpected_ai_text rule (plan section 20)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from figure_tools.validation.extractors.raster_ocr import (
    OCRBackend,
    PaddleOCRBackend,
    detect_text_elements,
    get_ocr_backend,
)
from figure_tools.validation.models import LayoutElement, PixelBBox
from figure_tools.validation.rules.ai_asset import unexpected_ai_text


class _FakeOCR:
    """Minimal OCR backend returning canned elements."""

    def __init__(self, elements):
        self._elements = elements
        self.calls = []

    def detect(self, image_path):
        self.calls.append(str(image_path))
        return list(self._elements)


def test_paddleocr_backend_returns_empty_when_not_installed(tmp_path: Path):
    img = tmp_path / "a.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(img)
    backend = PaddleOCRBackend()
    # paddleocr is not installed in the test env -> no crash, empty result.
    assert backend.detect(img) == []
    assert backend._unavailable is True


def test_get_ocr_backend_disabled():
    assert get_ocr_backend({"ocr": {"enabled": False}}) is None


def test_detect_text_elements_with_backend(tmp_path: Path):
    img = tmp_path / "a.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(img)
    els = [LayoutElement("ocr_0", "text", PixelBBox(5, 5, 30, 20),
                         text="hello", source="ocr", metadata={"confidence": 0.9})]
    backend = _FakeOCR(els)
    out = detect_text_elements(img, backend)
    assert len(out) == 1
    assert out[0].text == "hello"
    assert backend.calls == [str(img)]


def test_detect_text_elements_without_backend(tmp_path: Path):
    assert detect_text_elements(tmp_path / "a.png", None) == []


def test_unexpected_ai_text_flags_detections():
    els = [LayoutElement("ocr_0", "text", PixelBBox(5, 5, 30, 20),
                         text="label", source="ocr", metadata={"confidence": 0.9})]
    checks = unexpected_ai_text([("fiber", els), ("clean", [])])
    fails = [c for c in checks if c["status"] == "fail"]
    assert len(fails) == 1
    assert fails[0]["level"] == "error"
    assert fails[0]["element_ids"] == ["fiber"]
    assert fails[0]["method"] == "ocr"


def test_unexpected_ai_text_pass_when_clean():
    checks = unexpected_ai_text([("fiber", [])])
    assert checks[0]["status"] == "pass"


def test_ocr_backend_protocol_is_runtime_checkable():
    backend = _FakeOCR([])
    assert isinstance(backend, OCRBackend)
