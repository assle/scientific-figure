"""OCR fallback for raster assets without layout metadata (plan section 15).

OCR is an optional capability. The default backend (PaddleOCR) is imported
lazily; if it is not installed the backend returns an empty result and the
workflow continues unaffected. OCR is never used to validate numerical data in
Python plots or to replace Matplotlib/SVG layout metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from figure_tools.validation.models import LayoutElement, PixelBBox


@runtime_checkable
class OCRBackend(Protocol):
    def detect(self, image_path: str | Path) -> list[LayoutElement]:
        ...


class PaddleOCRBackend:
    """PaddleOCR-backed detector. Lazy-imports paddleocr; returns [] if the
    dependency is missing so the base workflow never fails."""

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._ocr: Any | None = None
        self._unavailable = False

    def _engine(self) -> Any | None:
        if self._unavailable:
            return None
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore[import-not-found]
            except Exception:  # noqa: BLE001
                self._unavailable = True
                return None
            try:
                self._ocr = PaddleOCR(use_angle_cls=True, lang=self._lang,
                                      show_log=False)
            except Exception:  # noqa: BLE001
                self._unavailable = True
                return None
        return self._ocr

    def detect(self, image_path: str | Path) -> list[LayoutElement]:
        engine = self._engine()
        if engine is None:
            return []
        try:
            result = engine.ocr(str(image_path), cls=True)
        except Exception:  # noqa: BLE001
            return []
        elements: list[LayoutElement] = []
        if not result:
            return elements
        for i, entry in enumerate(_flatten(result)):
            box, (text, conf) = _unpack_entry(entry)
            if not box or not text:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            elements.append(LayoutElement(
                element_id=f"ocr_{i}",
                element_type="text",
                bbox=PixelBBox(min(xs), min(ys), max(xs), max(ys)),
                text=text,
                font_size_pt=None,
                source="ocr",
                metadata={"confidence": float(conf)},
            ))
        return elements


def _flatten(result):
    """PaddleOCR returns nested lists across versions; yield leaf entries."""
    stack = [result]
    leaves: list = []
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            # A leaf entry is [box, (text, conf)]; detect by structure.
            if (len(item) == 2 and isinstance(item[0], list)
                    and isinstance(item[1], (list, tuple)) and len(item[1]) == 2):
                leaves.append(item)
            else:
                stack.extend(item)
    return leaves


def _unpack_entry(entry):
    try:
        box, rec = entry
        text, conf = rec
        return box, (text, conf)
    except Exception:  # noqa: BLE001
        return None, ("", 0.0)


def get_ocr_backend(config: dict[str, Any] | None = None) -> OCRBackend | None:
    """Build the configured OCR backend, or None if OCR is disabled/missing.

    ``enabled: auto`` (default) only activates the backend when the dependency
    is importable, detected cheaply via ``importlib`` (never initializes the
    engine, which could download models).
    """
    import importlib.util

    config = config or {}
    ocr_cfg = config.get("ocr", {})
    if not isinstance(ocr_cfg, dict):
        ocr_cfg = {}
    enabled = ocr_cfg.get("enabled", "auto")
    if enabled is False:
        return None
    backend_name = ocr_cfg.get("backend", "paddleocr")
    if backend_name == "paddleocr":
        if enabled == "auto" and importlib.util.find_spec("paddleocr") is None:
            return None
        return PaddleOCRBackend(lang=ocr_cfg.get("lang", "en"))
    return None


def detect_text_elements(
    image_path: str | Path,
    backend: OCRBackend | None,
) -> list[LayoutElement]:
    if backend is None:
        return []
    return backend.detect(image_path)


__all__ = [
    "OCRBackend",
    "PaddleOCRBackend",
    "get_ocr_backend",
    "detect_text_elements",
]
