"""Safe OpenCode configuration merger tests (plan section 14).

All tests use temp config files - the real opencode.json is never touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from figure_tools.config import deep_merge
from install.configure_opencode import (
    apply_merge,
    mcp_entry_for_python,
    propose_merge,
    render_diff,
)
from install.install_delivery import (
    InstallRequest,
    LegacyCodexDeliveryAdapter,
    LAUNCHER_MARKER,
    OpenCodeDeliveryAdapter,
    build_parser,
    delivery_paths,
    install,
    host_delivery_adapters,
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


def _stage_test_python(runtime_dir: Path, with_gui: bool = False) -> Path:
    python = runtime_dir / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True, exist_ok=True)
    gui_probe_status = 0 if with_gui else 1
    python.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        f"  *\"find_spec('PySide6')\"*) exit {gui_probe_status};;\n"
        "esac\n"
        f"exec {str(Path(sys.executable))!r} \"$@\"\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    return python


def _install(source_dir: Path, paths, **kwargs):
    install_opencode = kwargs.pop("install_opencode", True)
    install_codex = kwargs.pop("install_codex", True)
    with_gui = kwargs.pop("with_gui", False)
    if install_opencode and install_codex:
        target = "both"
    elif install_opencode:
        target = "opencode"
    elif install_codex:
        target = "codex-legacy"
    else:
        target = "runtime"
    request = InstallRequest(
        source_dir=source_dir,
        paths=paths,
        target=target,
        scope="global" if paths.scope_id == "global" else "project",
        product_version=paths.product_version,
        with_gui=with_gui,
    )
    return install(request, **kwargs)


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
    from figure_tools.jsonc_edit import load_jsonc

    merged = load_jsonc(text)
    assert "// a comment" in text
    assert merged["mcp"]["scientific-figure"] == MCP_ENTRY
    assert merged["mcp"]["other"]["command"] == ["x"]


def test_transactional_install_preserves_jsonc_comments_and_order(tmp_path: Path):
    config_home = tmp_path / "config"
    config = config_home / "opencode" / "opencode.jsonc"
    config.parent.mkdir(parents=True)
    original = """{
  // provider stays first
  "provider": {"custom": {"url": "https://example.test//v1"}},
  /* keep before MCP */
  "mcp": {
    "other": {"command": ["other"]}, // keep other
  },
  "permission": {"bash": "ask"},
}
"""
    config.write_text(original, encoding="utf-8")
    paths = delivery_paths(
        config_home=config_home,
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    _install(
        Path(__file__).resolve().parents[2],
        paths,
        runtime_sync=_stage_test_python,
        run_smoke_test=False,
        install_opencode=True,
        install_codex=False,
    )
    candidate = config.read_text(encoding="utf-8")
    assert candidate.index("provider") < candidate.index('"mcp"') < candidate.index("permission")
    for exact in (
        "// provider stays first",
        '"provider": {"custom": {"url": "https://example.test//v1"}}',
        "/* keep before MCP */",
        '"other": {"command": ["other"]}, // keep other',
        '"permission": {"bash": "ask"},',
    ):
        assert exact in candidate


def test_invalid_jsonc_fails_preflight_without_any_install_write(tmp_path: Path):
    config_home = tmp_path / "config"
    config = config_home / "opencode" / "opencode.jsonc"
    config.parent.mkdir(parents=True)
    original = '{"mcp": {/* unterminated}'
    config.write_text(original, encoding="utf-8")
    paths = delivery_paths(
        config_home=config_home,
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    with pytest.raises(ValueError, match="unterminated"):
        _install(
            Path(__file__).resolve().parents[2],
            paths,
            runtime_sync=_stage_test_python,
            install_opencode=True,
            install_codex=False,
        )
    assert config.read_text(encoding="utf-8") == original
    assert not paths.runtime_scope_dir.exists()
    assert not paths.transaction_log_dir.exists()


def test_delivery_paths_support_global_and_project_scopes(tmp_path: Path):
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    global_paths = delivery_paths(
        config_home=config_home,
        data_home=data_home,
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    assert global_paths.skill_dir == (
        config_home / "opencode" / "skills" / "scientific-figure-builder"
    )
    assert global_paths.config_file == config_home / "opencode" / "opencode.json"
    assert global_paths.launcher_file == tmp_path / "bin" / "scientific-figure"
    assert global_paths.runtime_dir == (
        tmp_path / "install" / "global" / "runtimes" / "0.3.1"
    )

    project = tmp_path / "project"
    project.mkdir()
    project_paths = delivery_paths(
        config_home=config_home,
        data_home=data_home,
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
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
        state_home=tmp_path / "state",
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
        state_home=tmp_path / "state",
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
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text(json.dumps(_existing_config()), encoding="utf-8")

    def _use_test_python(runtime_dir: Path, _with_gui: bool) -> Path:
        assert (runtime_dir / "figure_tools" / "server.py").is_file()
        return _stage_test_python(runtime_dir)

    result = _install(
        source,
        paths,
        runtime_sync=_use_test_python,
    )
    assert (paths.skill_dir / "SKILL.md").is_file()
    assert not (paths.skill_dir / "references").exists()
    assert paths.command_file.is_file()
    assert result.mcp_tools == 2
    assert result.active_runtime["version"] == "0.3.1"
    assert result.launcher.is_file()
    assert LAUNCHER_MARKER in result.launcher.read_text(encoding="utf-8")

    merged = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert merged["provider"] == _existing_config()["provider"]
    assert merged["mcp"]["other-server"] == _existing_config()["mcp"]["other-server"]
    assert merged["mcp"]["scientific-figure"]["command"][0] == str(
        paths.runtime_dir / ".venv" / "bin" / "python"
    )

    verified = verify_delivery(paths)
    assert verified["mcp_tools"] == 2
    assert verified["checks"]["launcher"] is True
    assert verified["checks"]["gui_resources"] is True
    assert verified["components"] == {"core": True, "gui": False}


def test_unrelated_global_launcher_blocks_install_before_changes(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    launcher = tmp_path / "bin" / "scientific-figure"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\necho unrelated\n", encoding="utf-8")
    paths = delivery_paths(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    with pytest.raises(RuntimeError, match="unrelated launcher"):
        _install(
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
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )

    def _use_test_python(_runtime_dir: Path, _with_gui: bool) -> Path:
        return _stage_test_python(_runtime_dir)

    first = _install(
        source,
        paths,
        runtime_sync=_use_test_python,
        run_smoke_test=False,
    )
    second = _install(
        source,
        paths,
        runtime_sync=_use_test_python,
        run_smoke_test=False,
    )
    assert first.runtime_backup is None
    assert second.runtime_backup is None
    assert len(list(paths.skill_dir.parent.glob("*/SKILL.md"))) == 1
    assert (paths.skill_dir / "SKILL.md").is_file()
    assert not paths.install_lock_dir.exists()
    assert not list(paths.staging_parent.glob("*"))
    assert not list(paths.transaction_backup_parent.glob("*"))
    assert len(list(paths.transaction_log_dir.glob("*.json"))) == 2
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
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    requested: list[bool] = []

    def _record_gui(_runtime_dir: Path, with_gui: bool) -> Path:
        requested.append(with_gui)
        return _stage_test_python(_runtime_dir)

    _install(
        source,
        paths,
        runtime_sync=_record_gui,
        run_smoke_test=False,
        with_gui=True,
    )
    assert requested == [True]


def test_installer_gui_option_is_explicit():
    parser = build_parser()
    assert parser.parse_args([]).target == "runtime"
    assert parser.parse_args([]).with_gui is False
    assert parser.parse_args(["--with-gui"]).with_gui is True
    assert parser.parse_args(["--codex"]).target == "runtime"
    assert parser.parse_args(["--opencode"]).target == "opencode"
    assert parser.parse_args(["--all"]).target == "both"
    assert parser.parse_args(["--runtime-only"]).target == "runtime"
    assert parser.parse_args(["--opencode-only"]).target == "opencode"
    assert parser.parse_args(["--codex-only"]).target == "codex-legacy"


def test_install_request_is_the_single_target_scope_and_version_interface(tmp_path: Path):
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    request = InstallRequest(
        source_dir=Path(__file__).resolve().parents[2],
        paths=paths,
        target="opencode",
        scope="global",
        product_version=paths.product_version,
        with_gui=True,
    )

    assert request.install_opencode is True
    assert request.install_codex is False
    assert request.with_gui is True
    assert isinstance(host_delivery_adapters(request)[0], OpenCodeDeliveryAdapter)
    with pytest.raises(ValueError, match="scope"):
        InstallRequest(
            source_dir=request.source_dir,
            paths=paths,
            target="runtime",
            scope="project",
            product_version=paths.product_version,
        )

    both = InstallRequest(
        source_dir=request.source_dir,
        paths=paths,
        target="both",
        scope="global",
        product_version=paths.product_version,
    )
    assert [type(adapter) for adapter in host_delivery_adapters(both)] == [
        OpenCodeDeliveryAdapter,
        LegacyCodexDeliveryAdapter,
    ]


def test_cli_translates_flags_into_an_install_request(tmp_path: Path, monkeypatch, capsys):
    import install.install_delivery as delivery

    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    captured = []
    monkeypatch.setattr(delivery, "delivery_paths", lambda **_kwargs: paths)
    monkeypatch.setattr(delivery, "read_product_version", lambda _source: paths.product_version)
    monkeypatch.setattr(
        delivery,
        "install",
        lambda request: captured.append(request) or SimpleNamespace(
            transaction_log=tmp_path / "transaction.json",
            mcp_tools=2,
            gui_installed=True,
            skill=paths.skill_dir,
            config=paths.config_file,
            codex_skill=paths.codex_skill_dir,
            codex_config=paths.codex_config_file,
            launcher=paths.launcher_file,
            launcher_warning=None,
            legacy_runtime_retained=None,
        ),
    )

    assert delivery.main([
        "--source-dir", str(Path(__file__).parents[2]),
        "--opencode", "--with-gui",
    ]) == 0

    assert captured[0].target == "opencode"
    assert captured[0].scope == "global"
    assert captured[0].with_gui is True
    assert "installed successfully" in capsys.readouterr().out


def test_runtime_only_install_does_not_publish_agent_integrations(tmp_path: Path):
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    result = _install(
        Path(__file__).resolve().parents[2],
        paths,
        runtime_sync=_stage_test_python,
        run_smoke_test=False,
        install_opencode=False,
        install_codex=False,
    )
    assert result.runtime.is_dir()
    assert result.launcher.is_file()
    assert not paths.skill_dir.exists()
    assert not paths.codex_skill_dir.exists()
    assert not paths.config_file.exists()
    assert not paths.codex_config_file.exists()


@pytest.mark.parametrize(
    ("install_opencode", "install_codex"),
    [(True, False), (False, True), (True, True)],
)
def test_host_install_targets_do_not_touch_unselected_agent(
    tmp_path: Path, install_opencode: bool, install_codex: bool,
):
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    _install(
        Path(__file__).resolve().parents[2],
        paths,
        runtime_sync=_stage_test_python,
        run_smoke_test=False,
        install_opencode=install_opencode,
        install_codex=install_codex,
    )
    assert paths.skill_dir.exists() is install_opencode
    assert paths.command_file.exists() is install_opencode
    assert paths.config_file.exists() is install_opencode
    assert paths.codex_skill_dir.exists() is install_codex
    assert paths.codex_config_file.exists() is install_codex


def test_verify_reports_optional_gui_and_can_require_it(tmp_path: Path, monkeypatch):
    import install.install_delivery as delivery

    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        install_home=tmp_path / "install",
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    _install(
        source,
        paths,
        runtime_sync=_stage_test_python,
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
        "state_home": tmp_path / "state",
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
        _install(
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
        state_home=tmp_path / "state",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    assert paths.legacy_runtime_dir is not None
    paths.legacy_runtime_dir.mkdir(parents=True)
    (paths.legacy_runtime_dir / "old.txt").write_text("rollback", encoding="utf-8")
    result = _install(
        Path(__file__).resolve().parents[2],
        paths,
        runtime_sync=_stage_test_python,
        run_smoke_test=False,
    )
    assert result.legacy_runtime_retained == paths.legacy_runtime_dir
    assert (paths.legacy_runtime_dir / "old.txt").read_text(encoding="utf-8") == "rollback"
    assert result.active_runtime["migrated_from"] == str(
        paths.legacy_runtime_dir.absolute()
    )


@pytest.mark.parametrize(
    "failure_stage",
    [
        "runtime",
        "opencode_skill",
        "codex_skill",
        "launcher",
        "opencode_command",
        "opencode_config",
        "codex_config",
        "active_runtime",
    ],
)
def test_failure_at_every_commit_stage_leaves_no_partial_install(
    tmp_path: Path, failure_stage: str,
):
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )

    def _inject(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"injected failure at {stage}")

    with pytest.raises(RuntimeError, match="injected failure"):
        _install(
            Path(__file__).resolve().parents[2],
            paths,
            runtime_sync=_stage_test_python,
            run_smoke_test=False,
            failure_injector=_inject,
        )

    for target in (
        paths.runtime_dir,
        paths.skill_dir,
        paths.command_file,
        paths.config_file,
        paths.codex_skill_dir,
        paths.codex_config_file,
        paths.launcher_file,
        paths.active_runtime_file,
    ):
        assert target is None or not target.exists(), (failure_stage, target)
    assert not paths.install_lock_dir.exists()
    assert not list(paths.staging_parent.glob("*"))
    assert not list(paths.transaction_backup_parent.glob("*"))
    log = json.loads(next(paths.transaction_log_dir.glob("*.json")).read_text())
    assert log["status"] == "rolled_back"


def test_late_failure_restores_existing_installation_byte_for_byte(tmp_path: Path):
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    source = Path(__file__).resolve().parents[2]
    _install(
        source,
        paths,
        runtime_sync=_stage_test_python,
        run_smoke_test=False,
    )
    marker = paths.skill_dir / "existing-marker.txt"
    marker.write_text("preserve me", encoding="utf-8")
    before = {
        path: path.read_bytes()
        for path in (
            paths.command_file,
            paths.config_file,
            paths.codex_config_file,
            paths.launcher_file,
            paths.active_runtime_file,
        )
        if path is not None
    }

    def _late_failure(stage: str) -> None:
        if stage == "codex_config":
            raise RuntimeError("late failure")

    with pytest.raises(RuntimeError, match="late failure"):
        _install(
            source,
            paths,
            runtime_sync=_stage_test_python,
            run_smoke_test=False,
            failure_injector=_late_failure,
        )

    assert marker.read_text(encoding="utf-8") == "preserve me"
    for path, content in before.items():
        assert path.read_bytes() == content


def test_preflight_rejects_insufficient_disk_before_writes(tmp_path: Path, monkeypatch):
    import install.install_delivery as delivery

    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
    )
    disk_usage = delivery.shutil.disk_usage(Path(__file__).anchor)
    monkeypatch.setattr(
        delivery.shutil,
        "disk_usage",
        lambda _path: type(disk_usage)(disk_usage.total, disk_usage.used, 1),
    )
    with pytest.raises(RuntimeError, match="insufficient disk space"):
        _install(
            Path(__file__).resolve().parents[2],
            paths,
            runtime_sync=_stage_test_python,
            install_opencode=False,
            install_codex=False,
        )
    assert not paths.runtime_scope_dir.exists()
    assert not paths.transaction_log_dir.exists()
