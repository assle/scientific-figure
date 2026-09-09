"""Observable local version-convergence status."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from figure_tools import __version__
from figure_tools.__main__ import main
from figure_tools.convergence import cleanup_local_versions
from figure_tools.install_paths import (
    PathEnvironment,
    native_plugin_cache_dir,
    release_cache_dir,
    resolve_delivery_paths,
)
from figure_tools.local_status import (
    RunningRuntimeInstance,
    LocalStatusRequest,
    PluginInstallation,
    collect_local_status,
    discover_running_runtime_instances,
    status_from_system,
)


def _environment(tmp_path: Path) -> PathEnvironment:
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
        platform_name="posix",
    )


def _active_install(tmp_path: Path, version: str = "0.6.0") -> tuple[PathEnvironment, Path]:
    environment = _environment(tmp_path)
    paths = resolve_delivery_paths(environment, version)
    paths.runtime_dir.mkdir(parents=True)
    paths.active_runtime_file.parent.mkdir(parents=True, exist_ok=True)
    paths.active_runtime_file.write_text(
        json.dumps({
            "version": version,
            "runtime_dir": str(paths.runtime_dir),
            "scope": "global",
        }),
        encoding="utf-8",
    )
    return environment, paths.runtime_dir


def test_status_requires_host_reload_when_running_mcp_uses_old_runtime(
    tmp_path: Path,
) -> None:
    environment, _runtime = _active_install(tmp_path)
    old_runtime = environment.install_root / "global" / "runtimes" / "0.5.1"
    old_runtime.mkdir(parents=True)

    result = collect_local_status(
        LocalStatusRequest(environment=environment, cli_version="0.6.0"),
        plugin=PluginInstallation(
            installed=True, enabled=True, version="0.6.0",
        ),
        running_instances=[
            RunningRuntimeInstance(
                pid=42,
                parent_pid=7,
                kind="mcp",
                version="0.5.1",
                executable=old_runtime / ".venv" / "bin" / "python",
            ),
        ],
    )

    assert result.conclusion == "restart_required"
    assert result.exit_code == 2
    assert result.target_version == "0.6.0"
    assert result.stale_instances == (42,)
    assert old_runtime in result.in_use_runtimes


def test_status_treats_on_demand_processes_as_healthy_when_idle(
    tmp_path: Path,
) -> None:
    environment, _runtime = _active_install(tmp_path)

    result = collect_local_status(
        LocalStatusRequest(environment=environment, cli_version="0.6.0"),
        plugin=PluginInstallation(
            installed=True, enabled=True, version="0.6.0",
        ),
        running_instances=[],
    )

    assert result.conclusion == "converged"
    assert result.exit_code == 0
    assert result.running_instances == ()


def test_remote_release_comparison_reports_update_available(tmp_path: Path) -> None:
    environment, _runtime = _active_install(tmp_path, "0.5.1")

    result = collect_local_status(
        LocalStatusRequest(
            environment=environment,
            cli_version="0.5.1",
            published_version="0.6.0",
        ),
        plugin=PluginInstallation(True, True, "0.5.1"),
        running_instances=[],
    )

    assert result.conclusion == "update_available"
    assert result.exit_code == 3
    assert result.published_version == "0.6.0"


def test_newer_local_candidate_is_not_reported_as_update_available(
    tmp_path: Path,
) -> None:
    environment, _runtime = _active_install(tmp_path, "0.7.0")
    result = collect_local_status(
        LocalStatusRequest(
            environment=environment,
            cli_version="0.7.0",
            published_version="0.6.0",
            require_plugin=False,
        ),
        plugin=PluginInstallation(False, False, None),
        running_instances=[],
    )

    assert result.conclusion == "converged"


def test_opencode_only_status_does_not_require_native_codex_plugin(
    tmp_path: Path,
) -> None:
    environment, _runtime = _active_install(tmp_path, "0.6.0")

    result = collect_local_status(
        LocalStatusRequest(
            environment=environment,
            cli_version="0.6.0",
            require_plugin=False,
        ),
        plugin=PluginInstallation(False, False, None),
        running_instances=[],
    )

    assert result.conclusion == "converged"
    assert result.exit_code == 0


def test_runtime_only_system_status_does_not_invent_codex_requirement(
    tmp_path: Path,
) -> None:
    environment, _runtime = _active_install(tmp_path, "0.6.0")

    result = collect_local_status(
        LocalStatusRequest(
            environment=environment,
            cli_version="0.6.0",
            require_plugin=False,
        ),
        plugin=PluginInstallation(False, False, None),
        running_instances=[],
    )

    assert result.conclusion == "converged"


def test_runtime_only_status_from_system_is_converged(tmp_path: Path) -> None:
    environment, _runtime = _active_install(tmp_path, "0.6.0")
    environ = {
        "XDG_CONFIG_HOME": str(environment.config_root),
        "XDG_DATA_HOME": str(environment.data_root),
        "XDG_STATE_HOME": str(environment.state_root),
        "XDG_CACHE_HOME": str(environment.cache_root),
        "XDG_RUNTIME_DIR": str(environment.session_root),
        "SCIENTIFIC_FIGURE_INSTALL_HOME": str(environment.install_root),
        "SCIENTIFIC_FIGURE_BIN_DIR": str(environment.launcher_dir),
        "CODEX_HOME": str(environment.codex_home),
        "PATH": "",
    }

    result = status_from_system("0.6.0", environ=environ)

    assert result.conclusion == "converged"
    assert result.plugin.installed is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX fake Codex adapter")
def test_status_cli_reports_one_json_result_without_starting_components(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    environment, _runtime = _active_install(tmp_path, __version__)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    codex = fake_bin / "codex"
    codex.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' '{\"installed\":[{\"name\":\"scientific-figure-builder\","
        f"\"installed\":true,\"enabled\":true,\"version\":\"{__version__}\"}}]}}'\n",
        encoding="utf-8",
    )
    codex.chmod(0o755)
    for key, value in {
        "XDG_CONFIG_HOME": environment.config_root,
        "XDG_DATA_HOME": environment.data_root,
        "XDG_STATE_HOME": environment.state_root,
        "XDG_CACHE_HOME": environment.cache_root,
        "XDG_RUNTIME_DIR": environment.session_root,
        "SCIENTIFIC_FIGURE_INSTALL_HOME": environment.install_root,
        "SCIENTIFIC_FIGURE_BIN_DIR": environment.launcher_dir,
        "CODEX_HOME": environment.codex_home,
    }.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])

    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conclusion"] == "converged"
    assert payload["target_version"] == __version__
    assert payload["running_instances"] == []


def test_on_demand_cleanup_removes_only_versions_without_running_processes(
    tmp_path: Path,
) -> None:
    environment, active_runtime = _active_install(tmp_path, "0.6.0")
    old_runtime = active_runtime.parent / "0.5.1"
    old_runtime.mkdir()
    old_python = old_runtime / ".venv" / "bin" / "python"
    old_python.parent.mkdir(parents=True)
    old_python.write_text("", encoding="utf-8")
    plugin_cache = native_plugin_cache_dir(environment)
    (plugin_cache / "0.5.1").mkdir(parents=True)
    (plugin_cache / "0.6.0").mkdir()

    blocked = cleanup_local_versions(
        environment,
        running_instances=[RunningRuntimeInstance(
            pid=42, parent_pid=1, kind="mcp", version="0.5.1",
            executable=old_python,
        )],
    )
    assert blocked == ()
    assert old_runtime.is_dir()
    assert (plugin_cache / "0.5.1").is_dir()

    removed = cleanup_local_versions(environment, running_instances=[])
    assert old_runtime in removed
    assert not (plugin_cache / "0.5.1").exists()


def test_process_discovery_uses_invoked_venv_path_instead_of_symlink_target(
    tmp_path: Path, monkeypatch
) -> None:
    import psutil

    environment, runtime = _active_install(tmp_path, "0.6.0")
    invoked = runtime / ".venv" / "bin" / "python"
    invoked.parent.mkdir(parents=True)
    invoked.write_text("", encoding="utf-8")

    class Process:
        info = {
            "pid": 42,
            "ppid": 1,
            "exe": "/shared/uv/python",
            "cmdline": [str(invoked), "-m", "figure_tools.server"],
        }

    monkeypatch.setattr(psutil, "process_iter", lambda _fields: [Process()])

    instances = discover_running_runtime_instances(environment)

    assert len(instances) == 1
    assert instances[0].version == "0.6.0"
    assert instances[0].executable == invoked


def test_status_reports_cleanup_state_without_mutating_it(tmp_path: Path) -> None:
    environment, active_runtime = _active_install(tmp_path, "0.6.0")
    paths = resolve_delivery_paths(environment, "0.6.0")
    old_runtime = active_runtime.parent / "0.5.1"
    old_runtime.mkdir()
    old_plugin = native_plugin_cache_dir(environment) / "0.5.1"
    old_plugin.mkdir(parents=True)
    staging = paths.staging_parent / "unfinished"
    staging.mkdir(parents=True)
    backup = paths.transaction_backup_parent / "unfinished"
    backup.mkdir(parents=True)
    download = release_cache_dir(environment) / "0.6.0"
    download.mkdir(parents=True)

    result = collect_local_status(
        LocalStatusRequest(
            environment=environment, cli_version="0.6.0", require_plugin=False,
        ),
        plugin=PluginInstallation(False, False, None),
        running_instances=[],
    )

    assert result.clean is False
    assert result.retained_runtimes == (old_runtime,)
    assert result.superseded_plugin_caches == (old_plugin,)
    assert result.staging_paths == (staging,)
    assert result.transaction_backup_paths == (backup,)
    assert result.release_cache_paths == (download,)
    assert old_runtime.is_dir()
