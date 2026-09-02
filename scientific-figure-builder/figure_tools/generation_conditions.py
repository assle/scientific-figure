"""Compile scientific asset intent into one Provider-neutral condition."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from figure_tools.provenance import hash_json


_STYLE_FIELDS = (
    "palette",
    "view",
    "projection",
    "lighting",
    "material",
    "background",
    "shadow",
    "stroke_widths",
)
_REFERENCE_ROLES = frozenset({"content", "style", "structure", "parent", "mask"})
_SECRET_KEYS = frozenset({"api_key", "secret", "token", "password", "credential"})


class GenerationConditionError(ValueError):
    """The requested generation condition cannot be compiled safely."""


def _reject_secrets(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS:
                raise GenerationConditionError(
                    f"secret-bearing input field {key!r} is not allowed"
                )
            _reject_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_secrets(item)


def _compile_references(
    references: Any,
    capabilities: Mapping[str, Any],
) -> list[dict[str, Any]]:
    compiled: list[dict[str, Any]] = []
    for raw in references or []:
        if not isinstance(raw, Mapping):
            raise GenerationConditionError("every reference must be an object")
        role = str(raw.get("role") or "")
        if role not in _REFERENCE_ROLES:
            raise GenerationConditionError(f"unsupported reference role {role!r}")
        capability = (
            "supports_structure_control"
            if role == "structure"
            else "supports_mask_edit"
            if role == "mask"
            else "supports_reference_image"
        )
        if not bool(capabilities.get(capability, False)):
            raise GenerationConditionError(
                f"reference role {role!r} requires {capability}"
            )
        strength = float(raw.get("strength", 1.0))
        if not 0 <= strength <= 1:
            raise GenerationConditionError("reference strength must be between 0 and 1")
        path = str(raw.get("path") or "")
        content_hash = str(raw.get("content_hash") or "")
        if not path or not content_hash:
            raise GenerationConditionError("reference path and content_hash are required")
        compiled.append({
            "role": role,
            "path": path,
            "content_hash": content_hash,
            "strength": strength,
        })
    if len(compiled) > 1 and not bool(
        capabilities.get("supports_multi_reference", False)
    ):
        raise GenerationConditionError(
            "multiple references require supports_multi_reference"
        )
    return sorted(
        compiled,
        key=lambda item: (item["role"], item["content_hash"], item["path"]),
    )


def compile_generation_condition(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical, cache-addressable condition for one raster asset."""

    _reject_secrets(request)
    asset_id = str(request["asset_id"])
    model_role = str(request.get("model_role") or "image_generate")
    style = dict(request.get("style_bible") or {})
    publication = dict(request.get("publication_profile") or {})
    parameters = {
        str(key): value
        for key, value in sorted(dict(request.get("parameters") or {}).items())
    }
    capabilities = dict(request.get("provider_capabilities") or {})
    references = _compile_references(request.get("references"), capabilities)

    style_contract = {
        field: style[field]
        for field in _STYLE_FIELDS
        if style.get(field) not in (None, "", {}, [])
    }
    forbidden = [str(item) for item in style.get("forbidden_elements", [])]
    negative_items = [
        "no text",
        "no symbols",
        "no watermark",
        *forbidden,
    ]
    negative_constraints = "; ".join(dict.fromkeys(negative_items))
    prompt_parts = [
        str(request.get("scientific_intent") or "").strip(),
        str(request.get("prompt") or "").strip(),
        "Style contract: " + json.dumps(
            style_contract, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ),
        "Publication profile: " + json.dumps(
            publication, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ),
        "Generate one isolated non-quantitative asset on a transparent background.",
        "Negative constraints: " + negative_constraints,
    ]
    prompt = "\n".join(part for part in prompt_parts if part)

    condition: dict[str, Any] = {
        "schema_version": "1.0",
        "asset_id": asset_id,
        "model_role": model_role,
        "prompt": prompt,
        "negative_constraints": negative_constraints,
        "parameters": parameters,
        "references": references,
        "control": None,
        "publication_profile": publication,
        "warnings": [],
        "style_bible_hash": str(request.get("style_bible_hash") or ""),
        "publication_profile_hash": str(
            request.get("publication_profile_hash") or ""
        ),
    }
    condition["condition_hash"] = hash_json(condition)
    return condition


def add_reference_to_condition(
    condition: Mapping[str, Any],
    reference: Mapping[str, Any],
    provider_capabilities: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a new Execution condition without mutating its approved base."""

    _reject_secrets(reference)
    updated = {
        key: value for key, value in condition.items() if key != "condition_hash"
    }
    updated["references"] = _compile_references(
        [*condition.get("references", []), reference],
        provider_capabilities,
    )
    updated["condition_hash"] = hash_json(updated)
    return updated


__all__ = [
    "GenerationConditionError",
    "add_reference_to_condition",
    "compile_generation_condition",
]
