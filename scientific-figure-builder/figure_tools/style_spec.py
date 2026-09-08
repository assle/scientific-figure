"""Canonical style input normalization and Style Bible resolution."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from figure_tools._resources import schema_path, template_path
from figure_tools.provenance import hash_json
from figure_tools.run_store import schema_error_detail


class StyleResolutionError(ValueError):
    """A style input cannot be normalized or resolved safely."""


def _schema(name: str) -> dict[str, Any]:
    return json.loads(schema_path(name).read_text(encoding="utf-8"))


STYLE_SPEC_SCHEMA = _schema("style-spec.schema.json")
STYLE_BIBLE_SCHEMA = _schema("style-bible.schema.json")
STYLE_INPUT_SCHEMA = {
    "oneOf": [
        {"type": "null"},
        {"type": "string", "minLength": 1},
        STYLE_SPEC_SCHEMA,
        STYLE_BIBLE_SCHEMA,
    ]
}


def _validate(value: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> None:
    detail = schema_error_detail(value, schema)
    if detail:
        raise StyleResolutionError(f"invalid {label}: {detail}")


def normalize_style_input(value: Any) -> dict[str, Any] | None:
    """Convert legacy and canonical style inputs to one persisted StyleSpec."""

    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise StyleResolutionError("style must not be empty")
        if text == "default":
            return {"kind": "default"}
        candidate = Path(text)
        if candidate.is_absolute() or candidate.suffix.lower() == ".json":
            return {"kind": "file", "path": text}
        return {"kind": "description", "description": text}
    if not isinstance(value, Mapping):
        raise StyleResolutionError("style must be a string, object, or null")
    item = copy.deepcopy(dict(value))
    if "kind" in item:
        _validate(item, STYLE_SPEC_SCHEMA, "StyleSpec")
        if item["kind"] == "inline":
            _validate(item["style_bible"], STYLE_BIBLE_SCHEMA, "Style Bible")
        return item
    _validate(item, STYLE_BIBLE_SCHEMA, "Style Bible")
    return {"kind": "inline", "style_bible": item}


def normalize_request_style(request: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(request))
    if "style" in result:
        result["style"] = normalize_style_input(result.get("style"))
    return result


def resolve_style_bible(
    value: Any,
    *,
    advice_style_bible: Mapping[str, Any] | None = None,
    base_dir: str | Path = ".",
) -> tuple[dict[str, Any], dict[str, str]]:
    spec = normalize_style_input(value) or {"kind": "default"}
    kind = str(spec["kind"])
    if kind == "default":
        bible = json.loads(template_path("default-style-bible.json").read_text(encoding="utf-8"))
    elif kind == "inline":
        bible = copy.deepcopy(dict(spec["style_bible"]))
    elif kind == "file":
        candidate = Path(str(spec["path"])).expanduser()
        if not candidate.is_absolute():
            candidate = Path(base_dir) / candidate
        if not candidate.is_file():
            raise StyleResolutionError(f"Style Bible file is missing: {candidate}")
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise StyleResolutionError(f"Style Bible file is unreadable: {candidate}") from exc
        if not isinstance(raw, Mapping):
            raise StyleResolutionError("Style Bible file must contain one JSON object")
        bible = dict(raw)
    elif kind == "description":
        if advice_style_bible is None:
            raise StyleResolutionError(
                "natural-language style needs a model-produced Style Bible"
            )
        bible = copy.deepcopy(dict(advice_style_bible))
    else:  # pragma: no cover - guarded by StyleSpec validation
        raise StyleResolutionError(f"unsupported style kind: {kind}")
    _validate(bible, STYLE_BIBLE_SCHEMA, "Style Bible")
    return bible, {"kind": kind, "content_hash": hash_json(bible)}


def style_digest(style_bible: Mapping[str, Any]) -> str:
    palette = ", ".join(
        str(value) for value in list((style_bible.get("palette") or {}).values())[:3]
    )
    forbidden = ", ".join(
        str(value) for value in list(style_bible.get("forbidden_elements") or [])[:3]
    )
    return (
        "Style: "
        f"view={style_bible.get('view')}; "
        f"projection={style_bible.get('projection')}; "
        f"background={style_bible.get('background')}; "
        f"palette={palette or 'unspecified'}; "
        f"forbidden={forbidden or 'none'}"
    )


__all__ = [
    "STYLE_INPUT_SCHEMA",
    "STYLE_SPEC_SCHEMA",
    "StyleResolutionError",
    "normalize_request_style",
    "normalize_style_input",
    "resolve_style_bible",
    "style_digest",
]
