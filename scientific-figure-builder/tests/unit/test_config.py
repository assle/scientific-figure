"""Configuration merging and project initialization tests (plan section 5).

Layer precedence (low -> high):
  Skill defaults < user-local private < project < per-run overrides
"""

from __future__ import annotations

from pathlib import Path

import yaml

from figure_tools.config import configured_models, initialize_project, load_config

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


def test_model_placeholders_are_not_treated_as_configured(tmp_path: Path,
                                                          monkeypatch) -> None:
    user_config = tmp_path / "user-config.yaml"
    user_config.write_text(
        "models:\n  image_generate: {model: ep-user-gen}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SCIENTIFIC_FIGURE_CONFIG", str(user_config))
    assert configured_models(tmp_path) == {"image_generate": {"model": "ep-user-gen"}}


def test_models_merge_user_project_and_environment(tmp_path: Path,
                                                    monkeypatch) -> None:
    user_config = tmp_path / "user-config.yaml"
    user_config.write_text(
        "\n".join((
            "models:",
            "  image_generate: {model: ep-user-gen}",
            "  image_edit: {model: ep-user-edit}",
            "  vision_analyze: {model: ep-user-vision}",
            "  vision_validate: {model: ep-user-validate}",
        )) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SCIENTIFIC_FIGURE_CONFIG", str(user_config))
    initialize_project(tmp_path)
    project = tmp_path / PROJECT_CONFIG_NAME / "project.yaml"
    data = yaml.safe_load(project.read_text(encoding="utf-8"))
    data["models"]["image_edit"] = {
        "model": "ep-project-edit", "provider": "openai",
    }
    project.write_text(yaml.safe_dump(data), encoding="utf-8")

    models = configured_models(
        tmp_path,
        environ={"ARK_VISION_VALIDATE": "ep-env-validate"},
    )
    assert models == {
        "image_generate": {"provider": "openai", "model": "ep-user-gen"},
        "image_edit": {"provider": "openai", "model": "ep-project-edit"},
        "vision_analyze": {"provider": "anthropic", "model": "ep-user-vision"},
        "vision_validate": {"provider": "anthropic", "model": "ep-env-validate"},
    }


def test_load_config_has_three_canonical_model_roles(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    cfg = load_config(tmp_path)
    assert set(cfg["models"]) == {
        "image_generate", "vision_analyze", "vision_validate",
    }
    assert cfg["models"]["image_generate"]["provider"] == "openai"
    assert cfg["models"]["vision_analyze"]["provider"] == "anthropic"
    assert cfg["models"]["vision_validate"]["provider"] == "anthropic"


def test_load_config_has_agent_plan_provider_roots(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    providers = load_config(tmp_path)["providers"]

    assert providers == {
        "openai": {
            "type": "openai",
            "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "key_env": "ARK_API_KEY",
            "supports_image_edit": True,
        },
        "anthropic": {
            "type": "anthropic",
            "base_url": "https://ark.cn-beijing.volces.com/api/plan",
            "key_env": "ARK_API_KEY",
            "auth_scheme": "bearer",
            "messages_path": "/v1/messages",
        },
    }


def test_load_config_skill_defaults_provide_limits(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg["limits"]["max_quality_retries_per_asset"] == 2
    assert cfg["limits"]["independent_asset_concurrency"] == 2


def test_load_config_default_export_target_is_general(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg["export"]["export_target"] == "general"


def test_run_overrides_can_select_ppt_export_target(tmp_path: Path) -> None:
    cfg = load_config(
        tmp_path,
        run_overrides={"export": {"export_target": "ppt"}},
    )
    assert cfg["export"]["export_target"] == "ppt"
