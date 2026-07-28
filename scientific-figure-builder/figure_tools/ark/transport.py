"""Ark transport abstraction (plan section 17).

The transport layer is injectable so the client can be tested without paid
calls. A real HTTP transport is finalized in Phase 7 against verified Ark docs.
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw


class ArkError(Exception):
    pass


class RateLimitError(ArkError):
    pass


class ArkTransport:
    def post(
        self,
        role: str,
        model: str,
        payload: dict,
        image_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


def _transparent_circle_png(size: int = 1024) -> bytes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = size // 4
    cx = cy = size // 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(200, 40, 40, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class MockArkTransport(ArkTransport):
    """Deterministic, no-network transport for tests and offline runs."""

    def __init__(self, fail_once_roles: set[str] | None = None) -> None:
        self.fail_once_roles = set(fail_once_roles or set())
        self.calls: list[tuple[str, str]] = []
        self._failed: set[str] = set()

    def post(self, role, model, payload, image_paths=None):
        self.calls.append((role, model))
        if role in self.fail_once_roles and role not in self._failed:
            self._failed.add(role)
            raise RateLimitError("429 rate limited (mock)")
        return self._response(role, model, payload)

    def _response(self, role, model, payload):
        if role == "reference_analysis":
            return {
                "panels": [{"panel_id": "a", "bbox": [0.0, 0.0, 1.0, 1.0]}],
                "objects": [{"label": "fiber", "confidence": 0.82}],
                "text_candidates": [{"text": "10 um", "confidence": 0.6}],
                "confidence": 0.82,
                "uncertainties": ["core diameter read from datasheet"],
            }
        if role in ("generation", "edits"):
            return {"image_bytes": _transparent_circle_png(1024),
                    "model": model, "seed": 0}
        if role in ("validations", "final_validation"):
            return {
                "checks": [
                    {"check_id": "multimodal_semantic", "status": "pass",
                     "detail": "object count and style consistent"},
                ],
                "blocking": False,
            }
        raise ArkError(f"unknown role {role!r}")
