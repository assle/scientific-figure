"""Canonical installation and runtime path resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from figure_tools.install_paths import (
    APP_NAME,
    PathEnvironment,
    activate_runtime,
    active_runtime_matches,
    discover_runtime_directory,
    read_active_runtime,
    resolve_delivery_paths,
)


def _environment(tmp_path: Path, *, platform_name: str = "posix") -> PathEnvironment:
    return PathEnvironment.from_environ(
        {
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_RUNTIME_DIR": str(tmp_path / "session"),
            "SCIENTIFIC_FIGURE_INSTALL_HOME": str(tmp_path / "install"),
            "SCIENTIFIC_FIGURE_BIN_DIR": str(tmp_path / "bin"),
            "CODEX_HOME": str(tmp_path / "codex"),
        },
        home=tmp_path / "home",
        platform_name=platform_name,
    )


def test_posix_defaults_keep_payload_out_of_xdg_data(tmp_path: Path) -> None:
    environment = PathEnvironment.from_environ(
        {}, home=tmp_path, platform_name="posix"
    )
    paths = resolve_delivery_paths(environment, "0.2.0")
    assert environment.install_root == tmp_path / ".local" / "lib" / APP_NAME
    assert paths.runtime_dir == (
        environment.install_root / "global" / "runtimes" / "0.2.0"
    )
    assert environment.data_root not in paths.runtime_dir.parents
    assert paths.launcher_file == tmp_path / ".local" / "bin" / "scientific-figure"


def test_windows_defaults_use_a_user_program_prefix(tmp_path: Path) -> None:
    environment = PathEnvironment.from_environ({}, home=tmp_path, platform_name="nt")
    paths = resolve_delivery_paths(environment, "0.2.0")
    assert environment.install_root == (
        tmp_path / "AppData" / "Local" / "Programs" / "ScientificFigureBuilder"
    )
    assert paths.launcher_file is not None
    assert paths.launcher_file.name == "scientific-figure.cmd"


def test_absolute_xdg_overrides_are_honored(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    paths = resolve_delivery_paths(environment, "0.2.0")
    assert paths.state_dir.is_relative_to(tmp_path / "state")
    assert paths.cache_dir.is_relative_to(tmp_path / "cache")
    assert paths.session_dir.is_relative_to(tmp_path / "session")
    assert paths.legacy_runtime_dir == tmp_path / "data" / APP_NAME


def test_relative_path_override_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="XDG_CONFIG_HOME must be an absolute path"):
        PathEnvironment.from_environ(
            {"XDG_CONFIG_HOME": "relative"},
            home=tmp_path,
            platform_name="posix",
        )


def test_versions_and_projects_have_isolated_runtime_directories(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    global_v1 = resolve_delivery_paths(environment, "0.1.0")
    global_v2 = resolve_delivery_paths(environment, "0.2.0")
    project_a = resolve_delivery_paths(environment, "0.2.0", tmp_path / "project-a")
    project_b = resolve_delivery_paths(environment, "0.2.0", tmp_path / "project-b")
    assert global_v1.runtime_scope_dir == global_v2.runtime_scope_dir
    assert global_v1.runtime_dir != global_v2.runtime_dir
    assert project_a.runtime_scope_dir != global_v2.runtime_scope_dir
    assert project_a.runtime_scope_dir != project_b.runtime_scope_dir
    assert project_a.launcher_file is None
    assert project_a.legacy_runtime_dir is None


def test_active_runtime_switch_is_atomic_metadata(tmp_path: Path) -> None:
    paths = resolve_delivery_paths(_environment(tmp_path), "0.2.0")
    paths.runtime_dir.mkdir(parents=True)
    metadata = activate_runtime(paths)
    assert metadata["version"] == "0.2.0"
    assert active_runtime_matches(paths)
    assert read_active_runtime(paths.active_runtime_file) == metadata
    assert not list(paths.active_runtime_file.parent.glob(".active-runtime.json.tmp-*"))


def test_legacy_runtime_is_recorded_but_not_removed(tmp_path: Path) -> None:
    paths = resolve_delivery_paths(_environment(tmp_path), "0.2.0")
    assert paths.legacy_runtime_dir is not None
    paths.legacy_runtime_dir.mkdir(parents=True)
    paths.runtime_dir.mkdir(parents=True)
    metadata = activate_runtime(paths)
    assert metadata["migrated_from"] == str(paths.legacy_runtime_dir.absolute())
    assert paths.legacy_runtime_dir.is_dir()


def test_discover_runtime_honors_explicit_override(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (runtime / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    assert discover_runtime_directory(
        executable=tmp_path / ".venv" / "bin" / "python",
        module_file=tmp_path / "module" / "figure_tools" / "components.py",
        environ={"SCIENTIFIC_FIGURE_RUNTIME_DIR": str(runtime)},
    ) == runtime.absolute()


def test_invalid_active_runtime_metadata_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "active-runtime.json"
    path.write_text(json.dumps({"version": "0.2.0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid active runtime metadata"):
        read_active_runtime(path)
