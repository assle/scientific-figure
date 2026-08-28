"""Configuration merging and project initialization (plan section 5).

Layer precedence (low -> high):
  Skill defaults < user-local private < project < per-run overrides
"""

from __future__ import annotations

import copy
import os
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from figure_tools._resources import template_path

PROJECT_DIR_NAME = ".scientific-figure"
USER_CONFIG_DIR_NAME = "scientific-figure-builder"
PROJECT_IGNORES = "*.local\nsecrets.json\nprivate/\n"
MODEL_ROLES = (
    "phase_reasoning",
    "image_generate",
    "image_edit",
    "vision_analyze",
    "vision_validate",
)
ROLE_ENV_VARS = {
    "phase_reasoning": "SCI_FIG_PHASE_REASONING",
    "image_generate": "SCI_FIG_IMAGE_GENERATE",
    "image_edit": "SCI_FIG_IMAGE_EDIT",
    "vision_analyze": "SCI_FIG_VISION_ANALYZE",
    "vision_validate": "SCI_FIG_VISION_VALIDATE",
}
PLACEHOLDER_MODEL = "<fixed-model-or-endpoint-id>"
PROVIDER_TYPES = ("openai", "anthropic")
LEGACY_PROVIDER_PROTOCOLS = {
    "responses": "openai",
    "anthropic": "anthropic",
}


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_skill_defaults() -> dict[str, Any]:
    return yaml.safe_load(template_path("default-project.yaml").read_text(encoding="utf-8"))


def load_project_config(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir) / PROJECT_DIR_NAME / "project.yaml"
    if path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def user_config_path() -> Path:
    explicit_path = os.environ.get("SCIENTIFIC_FIGURE_CONFIG")
    if explicit_path:
        return Path(explicit_path)
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / USER_CONFIG_DIR_NAME / "config.yaml"


def load_user_config() -> dict[str, Any]:
    path = user_config_path()
    if path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def initialize_project(project_dir: str | Path, force: bool = False) -> dict[str, Any]:
    proj = Path(project_dir) / PROJECT_DIR_NAME
    proj.mkdir(parents=True, exist_ok=True)

    project_yaml = proj / "project.yaml"
    if force or not project_yaml.exists():
        project_yaml.write_text(template_path("default-project.yaml").read_text(encoding="utf-8"),
                                encoding="utf-8")

    style_bible = proj / "style_bible.json"
    if force or not style_bible.exists():
        style_bible.write_text(template_path("default-style-bible.json").read_text(encoding="utf-8"),
                               encoding="utf-8")

    gitignore = proj / ".gitignore"
    if force or not gitignore.exists():
        gitignore.write_text(PROJECT_IGNORES, encoding="utf-8")

    return load_config(project_dir)


def load_config(
    project_dir: str | Path,
    user_config: dict | None = None,
    run_overrides: dict | None = None,
) -> dict[str, Any]:
    cfg = load_skill_defaults()
    if user_config is not None:
        cfg = deep_merge(cfg, user_config)
    else:
        cfg = deep_merge(cfg, load_user_config())
    cfg = deep_merge(cfg, load_project_config(project_dir))
    if run_overrides:
        cfg = deep_merge(cfg, run_overrides)
    return cfg


def configured_models(
    project_dir: str | Path | None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    environment = os.environ if environ is None else environ
    user_cfg = load_user_config()
    project_cfg = load_project_config(project_dir) if project_dir is not None else {}
    models: dict[str, dict[str, Any]] = {}
    for role in MODEL_ROLES:
        role_cfg: dict[str, Any] = {}
        configured_model: str | None = None
        for source in (user_cfg, project_cfg):
            source_role = source.get("models", {}).get(role, {})
            if isinstance(source_role, dict):
                metadata = {
                    key: value for key, value in source_role.items()
                    if key != "model"
                }
                role_cfg = deep_merge(role_cfg, metadata)
                model = source_role.get("model")
                if (isinstance(model, str) and model.strip()
                        and model != PLACEHOLDER_MODEL):
                    configured_model = model
        env_model = environment.get(ROLE_ENV_VARS[role])
        if isinstance(env_model, str) and env_model.strip():
            configured_model = env_model
        if configured_model is not None:
            models[role] = dict(role_cfg, model=configured_model)
    return models


def configured_providers(project_dir: str | Path | None) -> dict[str, dict[str, Any]]:
    user_cfg = load_user_config()
    project_cfg = load_project_config(project_dir) if project_dir is not None else {}
    providers = deep_merge(
        user_cfg.get("providers", {}) if isinstance(user_cfg.get("providers"), dict) else {},
        project_cfg.get("providers", {}) if isinstance(project_cfg.get("providers"), dict) else {},
    )
    for name, provider in providers.items():
        provider_type = provider.get("type")
        legacy_protocol = provider.get("protocol")
        if legacy_protocol is not None:
            migrated_type = LEGACY_PROVIDER_PROTOCOLS.get(legacy_protocol)
            if migrated_type is None:
                raise ValueError(
                    f"provider {name!r} has unsupported legacy protocol "
                    f"{legacy_protocol!r}; use type: openai or type: anthropic"
                )
            if provider_type is not None and provider_type != migrated_type:
                raise ValueError(
                    f"provider {name!r} has conflicting type {provider_type!r} "
                    f"and protocol {legacy_protocol!r}"
                )
            warnings.warn(
                f"provider {name!r}: protocol: {legacy_protocol} is deprecated; "
                f"use type: {migrated_type}",
                FutureWarning,
                stacklevel=2,
            )
            provider_type = migrated_type
            provider.pop("protocol", None)
            provider["type"] = provider_type
        if provider_type not in PROVIDER_TYPES:
            raise ValueError(
                f"provider {name!r} has unsupported type {provider_type!r}; "
                f"expected one of {', '.join(PROVIDER_TYPES)}"
            )
    return providers
