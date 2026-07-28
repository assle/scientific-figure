"""Configuration merging and project initialization tests (plan section 5).

Layer precedence (low -> high):
  Skill defaults < user-local private < project < per-run overrides
"""

from __future__ import annotations

from pathlib import Path

import yaml

from figure_tools.config import initialize_project, load_config

PROJECT_CONFIG_NAME = ".scientific-figure"


def test_initialize_project_creates_non_secret_config(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    proj = tmp_path / PROJECT_CONFIG_NAME
    assert (proj / "project.yaml").is_file()
    assert (proj / "style_bible.json").is_file()
    assert (proj / ".gitignore").is_file()
    blob = (proj / "project.yaml").read_text(encoding="utf-8").lower()
    for forbidden in ("api_key=", "secret=", "token=", "password="):
        assert forbidden not in blob


def test_initialize_project_is_idempotent(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    proj = tmp_path / PROJECT_CONFIG_NAME / "project.yaml"
    proj.write_text("schema_version: '9.9'\nmodels: {image_generate: {model: kept}}\n")
    initialize_project(tmp_path)  # must not overwrite
    data = yaml.safe_load(proj.read_text(encoding="utf-8"))
    assert data["schema_version"] == "9.9"
    assert data["models"]["image_generate"]["model"] == "kept"


def test_user_local_overrides_skill_defaults_without_project(tmp_path: Path) -> None:
    # No project file present: user-local wins over skill-default placeholders.
    cfg = load_config(
        tmp_path,
        user_config={
            "models": {"image_generate": {"model": "ep-user-gen"}},
            "export": {"dpi": 150},
        },
    )
    assert cfg["models"]["image_generate"]["model"] == "ep-user-gen"
    assert cfg["export"]["dpi"] == 150


def test_run_overrides_win_over_user_and_skill(tmp_path: Path) -> None:
    cfg = load_config(
        tmp_path,
        user_config={"models": {"image_generate": {"model": "ep-user-gen"}}},
        run_overrides={"models": {"image_generate": {"model": "ep-run-gen"}}},
    )
    assert cfg["models"]["image_generate"]["model"] == "ep-run-gen"


def test_project_overrides_user_local(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    proj = tmp_path / PROJECT_CONFIG_NAME / "project.yaml"
    data = yaml.safe_load(proj.read_text(encoding="utf-8"))
    data["export"]["dpi"] = 200
    proj.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(tmp_path, user_config={"export": {"dpi": 150}})
    assert cfg["export"]["dpi"] == 200  # project > user-local


def test_load_config_has_four_model_roles(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    cfg = load_config(tmp_path)
    for role in ("image_generate", "image_edit", "vision_analyze", "vision_validate"):
        assert role in cfg["models"]


def test_load_config_skill_defaults_provide_limits(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg["limits"]["max_quality_retries_per_asset"] == 2
    assert cfg["limits"]["independent_asset_concurrency"] == 2
