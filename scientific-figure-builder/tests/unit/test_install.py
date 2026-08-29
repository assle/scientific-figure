"""Safe OpenCode configuration merger tests (plan section 14).

All tests use temp config files - the real opencode.json is never touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PureWindowsPath

import pytest

from figure_tools.config import deep_merge
from install.configure_opencode import (
    apply_merge,
    mcp_entry_for_python,
    propose_merge,
    render_diff,
)
from install.install_delivery import (
    LAUNCHER_MARKER,
    build_parser,
    delivery_paths,
    install_delivery,
    launcher_text,
    sync_runtime,
    validate_launcher_target,
    verify_delivery,
)
from figure_tools.install_paths import activate_runtime, read_active_runtime

MCP_ENTRY = {
    "type": "local",
    "command": ["uv", "run", "python", "-m", "figure_tools.server"],
    "enabled": True,
}


def _existing_config():
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"anthropic": {"models": {"claude": {}}}},
        "mcp": {
            "other-server": {"type": "local", "command": ["bun", "x", "other"]},
        },
        "permission": {"bash": {"*": "ask"}},
        "agent": {"build": {"tools": {"bash": True}}},
        "tools": {"other-server_*": False},
        "command": {"test": {"template": "run tests"}},
    }


def test_propose_merge_adds_scientific_figure_mcp():
    existing = _existing_config()
    proposed = propose_merge(existing, "scientific-figure", MCP_ENTRY)
    assert proposed["mcp"]["scientific-figure"] == MCP_ENTRY
    assert proposed["$schema"] == "https://opencode.ai/config.json"
    # unrelated keys preserved
    assert proposed["provider"] == existing["provider"]
    assert proposed["mcp"]["other-server"] == existing["mcp"]["other-server"]
    assert proposed["permission"] == existing["permission"]
    assert proposed["agent"] == existing["agent"]
    assert proposed["tools"] == existing["tools"]
    assert proposed["command"] == existing["command"]


def test_propose_merge_updates_own_entry_preserves_others():
    existing = _existing_config()
    existing["mcp"]["scientific-figure"] = {"type": "local", "command": ["old"]}
    proposed = propose_merge(existing, "scientific-figure", MCP_ENTRY)
    assert proposed["mcp"]["scientific-figure"] == MCP_ENTRY  # updated
    assert proposed["mcp"]["other-server"]["command"] == ["bun", "x", "other"]


def test_propose_merge_does_not_mutate_input():
    existing = _existing_config()
    propose_merge(existing, "scientific-figure", MCP_ENTRY)
    assert "scientific-figure" not in existing["mcp"]


def test_apply_merge_writes_and_backs_up(tmp_path: Path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps(_existing_config(), indent=2), encoding="utf-8")
    result = apply_merge(cfg, "scientific-figure", MCP_ENTRY,
                         approver=lambda diff: True, backup=True)
    assert result["applied"] is True
    assert Path(result["backup"]).is_file()
    merged = json.loads(cfg.read_text(encoding="utf-8"))
    assert merged["mcp"]["scientific-figure"] == MCP_ENTRY
    # backup equals original
    assert json.loads(Path(result["backup"]).read_text(encoding="utf-8"))["mcp"][
        "other-server"]


def test_apply_merge_approver_false_does_not_write(tmp_path: Path):
    cfg = tmp_path / "opencode.json"
    original = json.dumps(_existing_config(), indent=2)
    cfg.write_text(original, encoding="utf-8")
    result = apply_merge(cfg, "scientific-figure", MCP_ENTRY,
                         approver=lambda diff: False, backup=True)
    assert result["applied"] is False
    assert cfg.read_text(encoding="utf-8") == original  # unchanged


def test_apply_merge_preserves_unrelated_providers_and_permissions(tmp_path: Path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps(_existing_config(), indent=2), encoding="utf-8")
    apply_merge(cfg, "scientific-figure", MCP_ENTRY, approver=lambda d: True)
    merged = json.loads(cfg.read_text(encoding="utf-8"))
    assert merged["provider"]["anthropic"]["models"]["claude"] == {}
    assert merged["permission"]["bash"]["*"] == "ask"
    assert merged["command"]["test"]["template"] == "run tests"


def test_render_diff_mentions_new_mcp():
    existing = _existing_config()
    proposed = propose_merge(existing, "scientific-figure", MCP_ENTRY)
    diff = render_diff(existing, proposed)
    assert "scientific-figure" in diff


def test_apply_merge_handles_jsonc_comments(tmp_path: Path):
    cfg = tmp_path / "opencode.jsonc"
    cfg.write_text(
        '{\n  // a comment\n  "mcp": {"other": {"type": "local", "command": ["x"]}}\n}\n',
        encoding="utf-8",
    )
    apply_merge(cfg, "scientific-figure", MCP_ENTRY, approver=lambda d: True)
    text = cfg.read_text(encoding="utf-8")
    merged = json.loads(text)
    assert merged["mcp"]["scientific-figure"] == MCP_ENTRY
    assert merged["mcp"]["other"]["command"] == ["x"]


def test_delivery_paths_support_global_and_project_scopes(tmp_path: Path):
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    global_paths = delivery_paths(
        config_home=config_home,
        data_home=data_home,
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    assert global_paths.skill_dir == (
        config_home / "opencode" / "skills" / "scientific-figure-builder"
    )
    assert global_paths.config_file == config_home / "opencode" / "opencode.json"
    assert global_paths.launcher_file == tmp_path / "bin" / "scientific-figure"
    assert global_paths.runtime_dir == (
        tmp_path / "install" / "global" / "runtimes" / "0.2.0"
    )

    project = tmp_path / "project"
    project.mkdir()
    project_paths = delivery_paths(
        config_home=config_home,
        data_home=data_home,
        install_home=tmp_path / "install",
        project_dir=project,
        codex_home=project / ".codex",
        bin_dir=tmp_path / "bin",
    )
    assert project_paths.skill_dir == (
        project / ".opencode" / "skills" / "scientific-figure-builder"
    )
    assert project_paths.config_file == project / "opencode.json"
    assert project_paths.launcher_file is None
    assert project_paths.runtime_dir != global_paths.runtime_dir


def test_delivery_paths_use_existing_jsonc_config(tmp_path: Path):
    config_home = tmp_path / "config"
    opencode_home = config_home / "opencode"
    opencode_home.mkdir(parents=True)
    jsonc = opencode_home / "opencode.jsonc"
    jsonc.write_text("{}\n", encoding="utf-8")
    paths = delivery_paths(
        config_home=config_home,
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    assert paths.config_file == jsonc


def test_project_delivery_paths_use_existing_dot_opencode_config(tmp_path: Path):
    project = tmp_path / "project"
    nested_config = project / ".opencode" / "opencode.json"
    nested_config.parent.mkdir(parents=True)
    nested_config.write_text("{}\n", encoding="utf-8")
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        project_dir=project,
        codex_home=project / ".codex",
        bin_dir=tmp_path / "bin",
    )
    assert paths.config_file == nested_config


def test_mcp_environment_forwards_model_and_endpoint_configuration(tmp_path: Path):
    entry = mcp_entry_for_python(tmp_path / "python")
    assert entry["environment"]["SCIENTIFIC_FIGURE_CONFIG"] == (
        "{env:SCIENTIFIC_FIGURE_CONFIG}"
    )
    assert entry["environment"]["OPENAI_API_KEY"] == "{env:OPENAI_API_KEY}"
    assert entry["environment"]["SCI_FIG_IMAGE_GENERATE"] == "{env:SCI_FIG_IMAGE_GENERATE}"


def test_install_delivery_is_discoverable_and_preserves_config(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text(json.dumps(_existing_config()), encoding="utf-8")

    def _use_test_python(runtime_dir: Path, _with_gui: bool) -> Path:
        assert (runtime_dir / "figure_tools" / "server.py").is_file()
        return Path(sys.executable)

    result = install_delivery(
        source,
        paths,
        runtime_sync=_use_test_python,
    )
    assert (paths.skill_dir / "SKILL.md").is_file()
    assert (paths.skill_dir / "references" / "routing-rules.md").is_file()
    assert paths.command_file.is_file()
    assert result["mcp_tools"] == 2
    assert result["active_runtime"]["version"] == "0.2.0"
    assert Path(result["launcher"]).is_file()
    assert LAUNCHER_MARKER in Path(result["launcher"]).read_text(encoding="utf-8")

    merged = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert merged["provider"] == _existing_config()["provider"]
    assert merged["mcp"]["other-server"] == _existing_config()["mcp"]["other-server"]
    assert merged["mcp"]["scientific-figure"]["command"][0] == str(
        Path(sys.executable).absolute()
    )

    verified = verify_delivery(paths)
    assert verified["mcp_tools"] == 2
    assert verified["checks"]["launcher"] is True
    assert verified["checks"]["gui_resources"] is True
    assert verified["components"] == {"core": True, "gui": True}


def test_unrelated_global_launcher_blocks_install_before_changes(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    launcher = tmp_path / "bin" / "scientific-figure"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\necho unrelated\n", encoding="utf-8")
    paths = delivery_paths(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    with pytest.raises(RuntimeError, match="unrelated launcher"):
        install_delivery(
            source,
            paths,
            runtime_sync=lambda _runtime, _with_gui: Path(sys.executable),
        )
    assert launcher.read_text(encoding="utf-8").startswith("#!/bin/sh\necho unrelated")


def test_launcher_target_validation_allows_our_marker(tmp_path: Path):
    launcher = tmp_path / "scientific-figure"
    launcher.write_text(launcher_text(Path(sys.executable)), encoding="utf-8")
    validate_launcher_target(launcher)


def test_windows_launcher_rendering_is_controlled():
    import install.install_delivery as delivery

    text = delivery.launcher_text(
        PureWindowsPath("C:/Program Files/Scientific Figure/.venv/Scripts/python.exe"),
        platform_name="nt",
    )
    assert text.startswith("@echo off")
    assert '"C:\\Program Files\\Scientific Figure\\.venv\\Scripts\\python.exe"' in text
    assert "%*" in text
    assert delivery.LAUNCHER_MARKER in text


def test_install_delivery_can_be_repeated_safely(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )

    def _use_test_python(_runtime_dir: Path, _with_gui: bool) -> Path:
        return Path(sys.executable)

    first = install_delivery(
        source,
        paths,
        runtime_sync=_use_test_python,
        run_smoke_test=False,
    )
    second = install_delivery(
        source,
        paths,
        runtime_sync=_use_test_python,
        run_smoke_test=False,
    )
    assert first["runtime_backup"] is None
    assert second["runtime_backup"] is not None
    assert Path(second["runtime_backup"]).is_dir()
    assert Path(second["skill_backup"]).parent.name == ".skill-backups"
    assert len(list(paths.skill_dir.parent.glob("*/SKILL.md"))) == 1
    assert (paths.skill_dir / "SKILL.md").is_file()
    merged = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert list(merged["mcp"]).count("scientific-figure") == 1


@pytest.mark.parametrize(
    ("with_gui", "expected_extra"),
    [(False, False), (True, True)],
)
def test_sync_runtime_installs_gui_only_when_requested(
    tmp_path: Path, monkeypatch, with_gui: bool, expected_extra: bool,
):
    import install.install_delivery as delivery

    runtime = tmp_path / "runtime"
    python = runtime / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(delivery.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(
        delivery.subprocess,
        "run",
        lambda command, check: calls.append(command),
    )

    assert sync_runtime(runtime, with_gui) == python.absolute()
    command = calls[0]
    assert ("--extra" in command) is expected_extra
    assert ("gui" in command) is expected_extra


def test_install_delivery_forwards_gui_selection(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    requested: list[bool] = []

    def _record_gui(_runtime_dir: Path, with_gui: bool) -> Path:
        requested.append(with_gui)
        return Path(sys.executable)

    install_delivery(
        source,
        paths,
        runtime_sync=_record_gui,
        run_smoke_test=False,
        with_gui=True,
    )
    assert requested == [True]


def test_installer_gui_option_is_explicit():
    parser = build_parser()
    assert parser.parse_args([]).with_gui is False
    assert parser.parse_args(["--with-gui"]).with_gui is True


def test_verify_reports_optional_gui_and_can_require_it(tmp_path: Path, monkeypatch):
    import install.install_delivery as delivery

    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    install_delivery(
        source,
        paths,
        runtime_sync=lambda _runtime, _with_gui: Path(sys.executable),
        run_smoke_test=False,
    )
    monkeypatch.setattr(delivery, "_gui_component_installed", lambda *_args: False)

    result = verify_delivery(paths)
    assert result["components"] == {"core": True, "gui": False}
    with pytest.raises(RuntimeError, match="gui_component"):
        verify_delivery(paths, require_gui=True)


def test_failed_upgrade_preserves_previous_active_runtime(tmp_path: Path):
    environment_kwargs = {
        "config_home": tmp_path / "config",
        "data_home": tmp_path / "data",
        "install_home": tmp_path / "install",
        "codex_home": tmp_path / "codex",
        "bin_dir": tmp_path / "bin",
    }
    previous = delivery_paths(product_version="0.1.0", **environment_kwargs)
    previous.runtime_dir.mkdir(parents=True)
    (previous.runtime_dir / "kept.txt").write_text("previous", encoding="utf-8")
    activate_runtime(previous)
    upgrade = delivery_paths(product_version="0.2.0", **environment_kwargs)

    def _fail_upgrade(_runtime: Path, _with_gui: bool) -> Path:
        raise RuntimeError("upgrade failed")

    with pytest.raises(RuntimeError, match="upgrade failed"):
        install_delivery(
            Path(__file__).resolve().parents[2],
            upgrade,
            runtime_sync=_fail_upgrade,
            run_smoke_test=False,
        )

    assert (previous.runtime_dir / "kept.txt").read_text(encoding="utf-8") == "previous"
    assert not upgrade.runtime_dir.exists()
    assert read_active_runtime(previous.active_runtime_file)["version"] == "0.1.0"


def test_successful_global_install_records_and_retains_legacy_runtime(tmp_path: Path):
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "legacy-data",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    assert paths.legacy_runtime_dir is not None
    paths.legacy_runtime_dir.mkdir(parents=True)
    (paths.legacy_runtime_dir / "old.txt").write_text("rollback", encoding="utf-8")
    result = install_delivery(
        Path(__file__).resolve().parents[2],
        paths,
        runtime_sync=lambda _runtime, _with_gui: Path(sys.executable),
        run_smoke_test=False,
    )
    assert result["legacy_runtime_retained"] == str(paths.legacy_runtime_dir)
    assert (paths.legacy_runtime_dir / "old.txt").read_text(encoding="utf-8") == "rollback"
    assert result["active_runtime"]["migrated_from"] == str(
        paths.legacy_runtime_dir.absolute()
    )
