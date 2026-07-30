"""AI-asset text rule: flag unexpected text in generated images (plan 11/15)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutElement
from figure_tools.validation.summary import make_check


def unexpected_ai_text(
    detections: list[tuple[str, list[LayoutElement]]],
) -> list[dict]:
    """``detections`` is a list of (asset_id, ocr_text_elements).

    AI-generated assets must contain no formal text (plan section 2). Any OCR
    detection on an image_asset is reported as an error.
    """
    checks: list[dict] = []
    found_any = False
    for asset_id, elements in detections:
        if not elements:
            continue
        found_any = True
        texts = [e.text for e in elements if e.text]
        first = elements[0]
        checks.append(make_check(
            "unexpected_ai_text", "final", "error", "fail",
            f"AI asset {asset_id} contains text: {texts!r}",
            element_ids=[asset_id],
            bbox=first.bbox.as_list(),
            confidence=first.metadata.get("confidence", 1.0),
            method="ocr",
            repair_action=f"regenerate {asset_id} without text, or remove text",
        ))
    if not found_any:
        checks.append(make_check("unexpected_ai_text", "final", "warning", "pass",
                                 "no unexpected text in AI assets"))
    return checks


__all__ = ["unexpected_ai_text"]
