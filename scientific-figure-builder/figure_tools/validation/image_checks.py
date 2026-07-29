"""Deterministic image-asset checks (plan section 11).

These never rely on visual judgment; they inspect pixels directly.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def _check_id(level: str, status: str, detail: str = "") -> dict:
    return {"level": level, "status": status, "detail": detail}


def deterministic_image_checks(
    image_path: str | Path,
    physical_size_mm: tuple[float, float] | None = None,
    min_dpi: int = 300,
) -> list[dict]:
    path = Path(image_path)
    checks: list[dict] = []

    # File integrity.
    try:
        img = Image.open(path)
        img.load()
        checks.append({"check_id": "file_integrity", "level": "error", "status": "pass",
                       "detail": f"{img.format} {img.mode}"})
    except Exception as e:  # noqa: BLE001
        checks.append({"check_id": "file_integrity", "level": "error", "status": "fail",
                       "detail": str(e)})
        return checks

    w, h = img.size
    checks.append({"check_id": "dimensions", "level": "error", "status": "pass",
                   "detail": f"{w}x{h}"})

    has_alpha = "A" in img.getbands()
    checks.append({
        "check_id": "alpha_channel", "level": "error",
        "status": "pass" if has_alpha else "fail",
        "detail": "alpha present" if has_alpha else "no alpha channel",
    })

    # Blank output: all pixels fully transparent (RGBA) or single uniform color.
    blank = False
    if has_alpha:
        extrema = img.getchannel("A").getextrema()
        if extrema == (0, 0):
            blank = True
    else:
        extrema = img.convert("L").getextrema()
        if extrema[0] == extrema[1]:
            blank = True
    checks.append({
        "check_id": "blank_output", "level": "error",
        "status": "fail" if blank else "pass",
        "detail": "fully blank" if blank else "has content",
    })

    # Effective DPI at final physical size.
    if physical_size_mm is not None:
        w_mm, h_mm = physical_size_mm
        dpi_w = w / (w_mm / 25.4)
        dpi_h = h / (h_mm / 25.4)
        effective = min(dpi_w, dpi_h)
        checks.append({
            "check_id": "effective_dpi", "level": "error",
            "status": "pass" if effective >= min_dpi else "fail",
            "detail": f"effective {effective:.0f} dpi (min {min_dpi})",
        })

    # Edge clipping / margins: non-transparent bbox must not touch the border.
    if has_alpha:
        bbox = img.getchannel("A").getbbox()
        margin_ok = bbox is not None and bbox[0] > 0 and bbox[1] > 0 and \
            bbox[2] < w and bbox[3] < h
        checks.append({
            "check_id": "edge_margins", "level": "warning",
            "status": "pass" if margin_ok else "fail",
            "detail": f"subject bbox {bbox}" if bbox else "no subject",
        })

    return checks
