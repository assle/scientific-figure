"""Headless authority for Provider types, Model roles, and route compatibility."""

from __future__ import annotations

import copy
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


PROVIDER_TYPES = ("openai", "anthropic")
LEGACY_PROVIDER_PROTOCOLS = {
    "responses": "openai",
    "anthropic": "anthropic",
}
PROVIDER_TYPE_FIELD_DEFAULTS: dict[str, Mapping[str, Any]] = {
    "openai": {"supports_image_edit": False},
    "anthropic": {
        "auth_scheme": "x-api-key",
        "messages_path": "/messages",
        "anthropic_version": "2023-06-01",
    },
}
PROVIDER_TYPE_SPECIFIC_FIELDS = frozenset(
    name
    for defaults in PROVIDER_TYPE_FIELD_DEFAULTS.values()
    for name in defaults
)
PLACEHOLDER_MODEL = "<fixed-model-or-endpoint-id>"
PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ModelRoleDefinition:
    role: str
    compatible_provider_types: tuple[str, ...]
    optional: bool = False
    inherits_from: str | None = None
    required_capability: str | None = None


MODEL_ROLE_CATALOG = (
    ModelRoleDefinition("phase_reasoning", PROVIDER_TYPES, optional=True),
    ModelRoleDefinition("image_generate", ("openai",)),
    ModelRoleDefinition(
        "image_edit",
        ("openai",),
        optional=True,
        inherits_from="image_generate",
        required_capability="supports_image_edit",
    ),
    ModelRoleDefinition("vision_analyze", PROVIDER_TYPES),
    ModelRoleDefinition("vision_validate", PROVIDER_TYPES),
)
MODEL_ROLES = tuple(item.role for item in MODEL_ROLE_CATALOG)
ROLE_ENV_VARS = {
    "phase_reasoning": "SCI_FIG_PHASE_REASONING",
    "image_generate": "SCI_FIG_IMAGE_GENERATE",
    "image_edit": "SCI_FIG_IMAGE_EDIT",
    "vision_analyze": "SCI_FIG_VISION_ANALYZE",
    "vision_validate": "SCI_FIG_VISION_VALIDATE",
}

_OPERATION_PATHS = (
    "/images/generations",
    "/v1/messages",
    "/responses",
    "/messages",
)


def normalize_provider_base_url(value: Any) -> str:
    root = str(value or "").strip().rstrip("/")
    for operation_path in _OPERATION_PATHS:
        if root.endswith(operation_path):
            return root[: -len(operation_path)]
    return root


def normalize_provider_id(provider_id: str) -> str:
    normalized = str(provider_id).strip()
    if not PROVIDER_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Provider ID must start with a lowercase letter and contain only "
            "lowercase letters, digits, '_' or '-' (1-64 characters)"
        )
    return normalized


def normalize_provider(
    provider_id: str,
    provider: Mapping[str, Any],
    *,
    warn_legacy: bool = True,
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(provider))
    provider_type = normalized.get("type")
    legacy_protocol = normalized.get("protocol")
    if legacy_protocol is not None:
        migrated_type = LEGACY_PROVIDER_PROTOCOLS.get(str(legacy_protocol))
        if migrated_type is None:
            raise ValueError(
                f"provider {provider_id!r} has unsupported legacy protocol "
                f"{legacy_protocol!r}; use type: openai or type: anthropic"
            )
        if provider_type is not None and str(provider_type) != migrated_type:
            raise ValueError(
                f"provider {provider_id!r} has conflicting type {provider_type!r} "
                f"and protocol {legacy_protocol!r}"
            )
        if warn_legacy:
            warnings.warn(
                f"provider {provider_id!r}: protocol: {legacy_protocol} is deprecated; "
                f"use type: {migrated_type}",
                FutureWarning,
                stacklevel=2,
            )
        provider_type = migrated_type
        normalized.pop("protocol", None)
    if provider_type not in PROVIDER_TYPES:
        raise ValueError(
            f"provider {provider_id!r} has unsupported type {provider_type!r}; "
            f"expected one of {', '.join(PROVIDER_TYPES)}"
        )
    provider_type = str(provider_type)
    normalized["type"] = provider_type
    if "base_url" in normalized:
        normalized["base_url"] = normalize_provider_base_url(normalized["base_url"])
    defaults = PROVIDER_TYPE_FIELD_DEFAULTS[provider_type]
    for name in PROVIDER_TYPE_SPECIFIC_FIELDS - defaults.keys():
        normalized.pop(name, None)
    for name, default in defaults.items():
        value = normalized.get(name, default)
        normalized[name] = (
            bool(value)
            if isinstance(default, bool)
            else str(value).strip() or default
        )
    return normalized


def normalize_providers(
    providers: Mapping[str, Mapping[str, Any]],
    *,
    warn_legacy: bool = True,
) -> dict[str, dict[str, Any]]:
    return {
        str(provider_id): normalize_provider(
            str(provider_id), provider, warn_legacy=warn_legacy
        )
        for provider_id, provider in providers.items()
    }


def configured_model_routes(
    config: Mapping[str, Any],
    *,
    environ: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    configured = config.get("models")
    source = configured if isinstance(configured, Mapping) else {}
    routes: dict[str, dict[str, Any]] = {}
    for role in MODEL_ROLES:
        raw = source.get(role)
        route = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
        model = route.get("model")
        environment_model = environ.get(ROLE_ENV_VARS[role])
        if isinstance(environment_model, str) and environment_model.strip():
            model = environment_model.strip()
        if not isinstance(model, str) or not model.strip() or model == PLACEHOLDER_MODEL:
            continue
        route["model"] = model.strip()
        routes[role] = route
    return routes


def merge_model_route_sources(
    sources: tuple[Mapping[str, Any], ...],
    *,
    environ: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Resolve layered Model routes without letting placeholders erase values."""

    merged: dict[str, dict[str, Any]] = {}
    for role in MODEL_ROLES:
        metadata: dict[str, Any] = {}
        model: str | None = None
        for source in sources:
            models = source.get("models")
            raw = models.get(role) if isinstance(models, Mapping) else None
            if not isinstance(raw, Mapping):
                continue
            metadata.update(
                copy.deepcopy({key: value for key, value in raw.items() if key != "model"})
            )
            candidate = raw.get("model")
            if (
                isinstance(candidate, str)
                and candidate.strip()
                and candidate != PLACEHOLDER_MODEL
            ):
                model = candidate.strip()
        environment_model = environ.get(ROLE_ENV_VARS[role])
        if isinstance(environment_model, str) and environment_model.strip():
            model = environment_model.strip()
        if model is not None:
            merged[role] = {**metadata, "model": model}
    return merged


def effective_model_route(
    role: str,
    models: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    route = models.get(role)
    if isinstance(route, Mapping):
        return copy.deepcopy(dict(route))
    definition = _definition(role)
    if definition.inherits_from:
        inherited = models.get(definition.inherits_from)
        if isinstance(inherited, Mapping):
            return copy.deepcopy(dict(inherited))
    return None


@dataclass(frozen=True)
class RouteCompatibility:
    role: str
    compatible: bool
    reason: str
    provider_id: str | None = None
    inherited: bool = False


def route_compatibility(
    role: str,
    models: Mapping[str, Mapping[str, Any]],
    providers: Mapping[str, Mapping[str, Any]],
) -> RouteCompatibility:
    definition = _definition(role)
    inherited = role not in models and definition.inherits_from is not None
    route = effective_model_route(role, models)
    if route is None:
        return RouteCompatibility(role, definition.optional, "optional route is not configured")
    provider_id = route.get("provider")
    if not isinstance(provider_id, str) or not provider_id:
        return RouteCompatibility(role, False, "route has no Provider ID")
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return RouteCompatibility(
            role, False, f"Provider {provider_id!r} is not configured", provider_id, inherited
        )
    provider_type = provider.get("type")
    if provider_type not in definition.compatible_provider_types:
        expected = " or ".join(definition.compatible_provider_types)
        return RouteCompatibility(
            role,
            False,
            f"role requires a {expected} Provider",
            provider_id,
            inherited,
        )
    capability = definition.required_capability
    if capability and not bool(provider.get(capability, False)):
        return RouteCompatibility(
            role,
            False,
            f"Provider must declare {capability}",
            provider_id,
            inherited,
        )
    return RouteCompatibility(role, True, "compatible", provider_id, inherited)


def _definition(role: str) -> ModelRoleDefinition:
    for definition in MODEL_ROLE_CATALOG:
        if definition.role == role:
            return definition
    raise ValueError(f"unknown Model role: {role}")


__all__ = [
    "LEGACY_PROVIDER_PROTOCOLS",
    "MODEL_ROLE_CATALOG",
    "MODEL_ROLES",
    "PLACEHOLDER_MODEL",
    "PROVIDER_TYPES",
    "PROVIDER_ID_PATTERN",
    "PROVIDER_TYPE_FIELD_DEFAULTS",
    "PROVIDER_TYPE_SPECIFIC_FIELDS",
    "ROLE_ENV_VARS",
    "ModelRoleDefinition",
    "RouteCompatibility",
    "configured_model_routes",
    "effective_model_route",
    "merge_model_route_sources",
    "normalize_provider",
    "normalize_provider_base_url",
    "normalize_provider_id",
    "normalize_providers",
    "route_compatibility",
]
