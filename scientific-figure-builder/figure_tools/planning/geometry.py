"""Shared normalized placement transformations for planned assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resolve_asset_bbox(
    asset: Mapping[str, Any],
    panel: Mapping[str, Any],
) -> list[float]:
    bbox = [float(value) for value in asset.get("bbox", panel["bbox"])]
    if asset.get("bbox_space") != "panel":
        return bbox
    px, py, pw, ph = (float(value) for value in panel["bbox"])
    x, y, width, height = bbox
    return [
        round(px + x * pw, 12),
        round(py + y * ph, 12),
        round(width * pw, 12),
        round(height * ph, 12),
    ]


__all__ = ["resolve_asset_bbox"]
