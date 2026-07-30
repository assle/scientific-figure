"""Evidence crop generation for layout failures (plan section 13).

For each failing check that carries a bounding box, produce a cropped,
scaled PNG with an optional bbox overlay so a human can locate the problem.
Evidence images are audit aids, not formal exports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


def generate_evidence(
    image_path: str | Path,
    checks: list[dict[str, Any]],
    evidence_dir: str | Path,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Annotate failing checks with ``evidence_path`` crops.

    Returns the checks list (mutated in place) with ``evidence_path`` set on
    each failing check that has a usable bbox.
    """
    config = config or {}
    pad = float(config.get("crop_padding_pixels", 30))
    scale = int(config.get("crop_scale", 4))
    if scale < 1:
        scale = 1
    draw_boxes = bool(config.get("draw_boxes", True))

    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(image_path).convert("RGBA")
    except Exception:  # noqa: BLE001
        return checks
    iw, ih = img.size

    counters: dict[str, int] = {}
    for c in checks:
        if c.get("status") != "fail":
            continue
        bbox = c.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x1 = max(0.0, min(iw, bbox[0] - pad))
        y1 = max(0.0, min(ih, bbox[1] - pad))
        x2 = max(0.0, min(iw, bbox[2] + pad))
        y2 = max(0.0, min(ih, bbox[3] + pad))
        if x2 <= x1 or y2 <= y1:
            continue
        crop = img.crop((int(x1), int(y1), int(x2), int(y2)))
        if draw_boxes:
            overlay = crop.copy()
            draw = ImageDraw.Draw(overlay, "RGBA")
            rx1 = bbox[0] - x1
            ry1 = bbox[1] - y1
            rx2 = bbox[2] - x1
            ry2 = bbox[3] - y1
            draw.rectangle((rx1, ry1, rx2, ry2), outline=(255, 0, 0, 200), width=2)
            crop = Image.alpha_composite(crop, overlay)
        new_w = max(1, int(crop.width * scale))
        new_h = max(1, int(crop.height * scale))
        crop = crop.resize((new_w, new_h), Image.NEAREST)

        cid = c.get("check_id", "issue")
        n = counters.get(cid, 0) + 1
        counters[cid] = n
        fname = f"{cid}_{n:03d}.png"
        path = evidence_dir / fname
        crop.save(path)
        c["evidence_path"] = str(path)

    return checks


__all__ = ["generate_evidence"]
