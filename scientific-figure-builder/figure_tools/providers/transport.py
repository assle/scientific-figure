"""Provider transport abstraction (plan section 17).

The transport layer is injectable so the client can be tested without paid
calls. A real HTTP transport is implemented by the provider adapters in
``generic_transport``, which speak the OpenAI-compatible (``/responses`` +
``/images/generations``), Anthropic-compatible (``/messages``), and scoped
DashScope Native image dialects.
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw

from figure_tools.provider_configuration import effective_model_route

ROLE_TO_MODEL_CONFIG = {
    "phase_reasoning": "phase_reasoning",
    "generation": "image_generate",
    "edits": "image_edit",
    "reference_analysis": "vision_analyze",
    "validations": "vision_validate",
    "final_validation": "vision_validate",
}


def model_config_for_role(
    models: dict[str, dict[str, Any]], role: str,
) -> tuple[str, dict[str, Any]] | None:
    config_role = ROLE_TO_MODEL_CONFIG.get(role)
    if config_role is None:
        return None
    model_config = effective_model_route(config_role, models)
    if config_role == "image_edit" and config_role not in models and model_config is not None:
        config_role = "image_generate"
    if model_config is None:
        return None
    return config_role, model_config


class ProviderError(Exception):
    pass


class RateLimitError(ProviderError):
    pass


class IncompleteStructuredResponseError(ProviderError):
    """A structured response stopped because its current output budget was too small."""

    def __init__(self, *, reason: str, attempted_max_output_tokens: int) -> None:
        self.reason = str(reason)
        self.attempted_max_output_tokens = int(attempted_max_output_tokens)
        super().__init__(f"incomplete structured response: {self.reason}")


class ProviderTransport:
    def capabilities(self) -> dict[str, bool]:
        return {}

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


class MockProviderTransport(ProviderTransport):
    """Deterministic, no-network transport for tests and offline runs."""

    def __init__(self, fail_once_roles: set[str] | None = None) -> None:
        self.fail_once_roles = set(fail_once_roles or set())
        self.calls: list[tuple[str, str]] = []
        self.requests: list[dict[str, Any]] = []
        self.local_region_calls: int = 0
        self._failed: set[str] = set()

    def post(self, role, model, payload, image_paths=None):
        self.calls.append((role, model))
        self.requests.append({
            "role": role,
            "model": model,
            "payload": payload,
            "image_paths": list(image_paths or []),
        })
        if payload.get("mode") == "local_region":
            self.local_region_calls += 1
        if role in self.fail_once_roles and role not in self._failed:
            self._failed.add(role)
            raise RateLimitError("429 rate limited (mock)")
        return self._response(role, model, payload)

    def capabilities(self) -> dict[str, bool]:
        return {
            "supports_image_edit": True,
            "supports_reference_image": True,
            "supports_multi_reference": True,
            "supports_mask_edit": True,
            "supports_structure_control": True,
            "supports_native_alpha": True,
            "supports_seed": True,
            "supports_candidate_batch": True,
        }

    def _response(self, role, model, payload):
        if role == "reference_analysis":
            return {
                "panels": [{"panel_id": "a", "bbox": [0.0, 0.0, 1.0, 1.0]}],
                "objects": [{"label": "fiber", "confidence": 0.82}],
                "text_candidates": [{"text": "10 um", "confidence": 0.6}],
                "confidence": 0.82,
                "uncertainties": ["core diameter read from datasheet"],
            }
        if role == "phase_reasoning":
            return payload["fallback_artifact"]
        if role in ("generation", "edits"):
            return {"image_bytes": _transparent_circle_png(2048),
                    "model": model, "seed": 0}
        if role in ("validations", "final_validation"):
            # Local-region verification returns a single verdict dict.
            if payload.get("mode") == "local_region":
                return {
                    "confirmed": True,
                    "confidence": 0.92,
                    "severity": "error",
                    "detail": "localized issue confirmed by vision model",
                    "move_element_id": (payload.get("context", {})
                                        .get("element_ids", [""])[0]),
                    "direction": "right",
                    "minimum_shift_px": 12,
                }
            return {
                "checks": [
                    {"check_id": "multimodal_semantic", "status": "pass",
                     "detail": "object count and style consistent"},
                    {"check_id": "legend_data_overlap", "status": "pass",
                     "detail": "legend does not overlap data"},
                    {"check_id": "text_overlap", "status": "pass",
                     "detail": "no text elements overlap"},
                    {"check_id": "label_readability", "status": "pass",
                     "detail": "tick labels are readable"},
                ],
                "blocking": False,
            }
        raise ProviderError(f"unknown role {role!r}")
