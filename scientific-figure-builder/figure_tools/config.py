"""Configuration merging and project initialization (plan section 5).

Layer precedence (low -> high):
  Skill defaults < user-local private < project < per-run overrides
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from figure_tools._resources import template_path

PROJECT_DIR_NAME = ".scientific-figure"
PROJECT_IGNORES = "*.local\nsecrets.json\nprivate/\n"


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
    if user_config:
        cfg = deep_merge(cfg, user_config)
    cfg = deep_merge(cfg, load_project_config(project_dir))
    if run_overrides:
        cfg = deep_merge(cfg, run_overrides)
    return cfg
