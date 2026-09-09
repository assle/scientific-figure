"""Local activation through a verified Product bundle."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

import pytest

from figure_tools.activation import ActivationRequest, CodexPluginAdapter, activate_local
from figure_tools.__main__ import main
from figure_tools.install_paths import (
    PathEnvironment,
    activate_runtime,
    read_active_runtime,
    resolve_delivery_paths,
)
from figure_tools.local_status import PluginInstallation
from figure_tools.local_status import LocalProcess
from figure_tools.release_bundle import ProductBundleRequest, build_product_bundle
from install.install_delivery import install_launcher


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_VERSION = str(tomllib.loads(
    (REPOSITORY_ROOT / "scientific-figure-builder" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
)["project"]["version"])


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


def _bundle(tmp_path: Path) -> Path:
    wheel = tmp_path / f"scientific_figure_builder-{PRODUCT_VERSION}-py3-none-any.whl"
    wheel.write_bytes(b"core-wheel")
    return build_product_bundle(ProductBundleRequest(
        repository_root=REPOSITORY_ROOT,
        output_dir=tmp_path / "release",
        product_version=PRODUCT_VERSION,
        source_commit="abc123",
        core_wheel=wheel,
    )).bundle


def _runtime_sync(runtime: Path, _with_gui: bool) -> Path:
    python = runtime / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' "
        "'{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}' "
        "'{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"tools\":[{},{}]}}'\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    return python


class PluginAdapter:
    def __init__(self) -> None:
        self.installed: list[tuple[Path, str]] = []

    def install(self, product_root: Path, version: str) -> PluginInstallation:
        self.installed.append((product_root, version))
        return PluginInstallation(True, True, version)

    def restore(self, version: str | None) -> None:
        del version
        return None

    def finalize(self) -> None:
        return None


def test_activation_installs_exact_bundle_and_preserves_user_configuration(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    provider_config = (
        environment.config_root / "scientific-figure-builder" / "config.yaml"
    )
    provider_config.parent.mkdir(parents=True)
    provider_config.write_text(
        "providers:\n  private:\n    credential_id: keep-me\n", encoding="utf-8"
    )
    plugin = PluginAdapter()

    result = activate_local(
        ActivationRequest(
            bundle=_bundle(tmp_path),
            environment=environment,
            expected_version=PRODUCT_VERSION,
            host="codex",
            with_gui=True,
        ),
        plugin_adapter=plugin,
        runtime_sync=_runtime_sync,
        processes=[],
    )

    assert result.conclusion == "converged"
    assert result.exit_code == 0
    assert result.product_version == PRODUCT_VERSION
    assert result.active_runtime.name == PRODUCT_VERSION
    assert plugin.installed[0][1] == PRODUCT_VERSION
    assert provider_config.read_text(encoding="utf-8").endswith(
        "credential_id: keep-me\n"
    )
    active = json.loads(
        (environment.install_root / "global" / "active-runtime.json").read_text()
    )
    assert active["version"] == PRODUCT_VERSION


def test_activation_restores_previous_converged_version_when_plugin_update_fails(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    previous = resolve_delivery_paths(environment, "0.5.0")
    previous.runtime_dir.mkdir(parents=True)
    previous_python = _runtime_sync(previous.runtime_dir, False)
    activate_runtime(previous)
    install_launcher(previous_python, previous.launcher_file)
    class FailingPlugin:
        def __init__(self) -> None:
            self.restored: list[str | None] = []

        def install(self, product_root: Path, version: str) -> PluginInstallation:
            del product_root, version
            raise RuntimeError("plugin update failed")

        def restore(self, version: str | None) -> None:
            self.restored.append(version)

        def finalize(self) -> None:
            return None

    plugin = FailingPlugin()
    with pytest.raises(RuntimeError, match="plugin update failed"):
        activate_local(
            ActivationRequest(
                bundle=_bundle(tmp_path),
                environment=environment,
                expected_version=PRODUCT_VERSION,
                host="codex",
            ),
            plugin_adapter=plugin,
            runtime_sync=_runtime_sync,
            processes=[],
        )

    active = read_active_runtime(previous.active_runtime_file)
    assert active is not None and active["version"] == "0.5.0"
    failed = resolve_delivery_paths(environment, PRODUCT_VERSION)
    assert not failed.runtime_dir.exists()
    assert previous.launcher_file is not None
    assert str(previous_python) in previous.launcher_file.read_text(encoding="utf-8")
    assert plugin.restored == ["0.5.0"]


def test_activation_restores_previous_version_when_plugin_finalize_fails(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    previous = resolve_delivery_paths(environment, "0.5.0")
    previous.runtime_dir.mkdir(parents=True)
    previous_python = _runtime_sync(previous.runtime_dir, False)
    activate_runtime(previous)
    install_launcher(previous_python, previous.launcher_file)

    class FinalizeFailure(PluginAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.restored: list[str | None] = []

        def finalize(self) -> None:
            raise RuntimeError("plugin finalize failed")

        def restore(self, version: str | None) -> None:
            self.restored.append(version)

    plugin = FinalizeFailure()
    with pytest.raises(RuntimeError, match="plugin finalize failed"):
        activate_local(
            ActivationRequest(
                bundle=_bundle(tmp_path), environment=environment,
                expected_version=PRODUCT_VERSION, host="codex",
            ),
            plugin_adapter=plugin,
            runtime_sync=_runtime_sync,
            processes=[],
        )

    active = read_active_runtime(previous.active_runtime_file)
    assert active is not None and active["version"] == "0.5.0"
    assert plugin.restored == ["0.5.0"]


def test_all_host_activation_restores_opencode_files_when_codex_plugin_fails(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    previous = resolve_delivery_paths(environment, "0.5.0")
    previous.runtime_dir.mkdir(parents=True)
    _runtime_sync(previous.runtime_dir, False)
    activate_runtime(previous)
    previous.skill_dir.mkdir(parents=True)
    (previous.skill_dir / "SKILL.md").write_text("old skill", encoding="utf-8")
    previous.command_file.parent.mkdir(parents=True)
    previous.command_file.write_text("old command", encoding="utf-8")
    previous.config_file.parent.mkdir(parents=True, exist_ok=True)
    previous.config_file.write_text(
        '{"unrelated":true,"mcp":{}}\n', encoding="utf-8"
    )

    class FailingPlugin(PluginAdapter):
        def install(self, product_root: Path, version: str) -> PluginInstallation:
            del product_root, version
            raise RuntimeError("plugin update failed")

    with pytest.raises(RuntimeError, match="plugin update failed"):
        activate_local(
            ActivationRequest(
                bundle=_bundle(tmp_path), environment=environment,
                expected_version=PRODUCT_VERSION, host="all",
            ),
            plugin_adapter=FailingPlugin(),
            runtime_sync=_runtime_sync,
            processes=[],
        )

    assert (previous.skill_dir / "SKILL.md").read_text() == "old skill"
    assert previous.command_file.read_text() == "old command"
    assert previous.config_file.read_text() == '{"unrelated":true,"mcp":{}}\n'


@pytest.mark.parametrize(
    ("old_processes", "expected_conclusion", "previous_exists"),
    [([], "converged", False), ([42], "restart_required", True)],
)
def test_activation_prunes_previous_runtime_only_after_process_convergence(
    tmp_path: Path,
    old_processes: list[int],
    expected_conclusion: str,
    previous_exists: bool,
) -> None:
    environment = _environment(tmp_path)
    previous = resolve_delivery_paths(environment, "0.5.0")
    previous.runtime_dir.mkdir(parents=True)
    previous_python = _runtime_sync(previous.runtime_dir, False)
    activate_runtime(previous)
    install_launcher(previous_python, previous.launcher_file)
    plugin_cache = (
        environment.codex_home / "plugins" / "cache" / "scientific-figure"
        / "scientific-figure-builder"
    )
    (plugin_cache / "0.5.0").mkdir(parents=True)
    (plugin_cache / PRODUCT_VERSION).mkdir()
    processes = [
        LocalProcess(
            pid=pid,
            parent_pid=1,
            kind="mcp",
            version="0.5.0",
            executable=previous_python,
        )
        for pid in old_processes
    ]

    result = activate_local(
        ActivationRequest(
            bundle=_bundle(tmp_path),
            environment=environment,
            expected_version=PRODUCT_VERSION,
            host="codex",
        ),
        plugin_adapter=PluginAdapter(),
        runtime_sync=_runtime_sync,
        processes=processes,
    )

    assert result.conclusion == expected_conclusion
    assert previous.runtime_dir.exists() is previous_exists
    assert (plugin_cache / "0.5.0").exists() is previous_exists
    assert (plugin_cache / PRODUCT_VERSION).is_dir()


def test_codex_plugin_adapter_replaces_and_can_restore_marketplace(
    tmp_path: Path, monkeypatch
) -> None:
    environment = _environment(tmp_path)
    stable = environment.install_root / "marketplace"
    stable.mkdir(parents=True)
    (stable / "old.txt").write_text("old", encoding="utf-8")
    product = tmp_path / "product"
    (product / ".agents" / "plugins").mkdir(parents=True)
    (product / ".agents" / "plugins" / "marketplace.json").write_text(
        '{"name":"scientific-figure","plugins":[]}', encoding="utf-8"
    )
    plugin_manifest = (
        product / "plugins" / "scientific-figure-builder" / ".codex-plugin"
    )
    plugin_manifest.mkdir(parents=True)
    (plugin_manifest / "plugin.json").write_text(
        json.dumps({"name": "scientific-figure-builder", "version": PRODUCT_VERSION}),
        encoding="utf-8",
    )
    codex = tmp_path / "codex"
    codex.write_text("", encoding="utf-8")
    responses = iter([
        {"marketplaces": [{
            "name": "scientific-figure",
            "marketplaceSource": {"sourceType": "local", "source": str(stable)},
        }]},
        {"installed": [{
            "name": "scientific-figure-builder", "installed": True,
            "enabled": True, "version": "0.5.0",
        }]},
        {},
        {},
        {"version": PRODUCT_VERSION, "installed": True, "enabled": True},
        {},
        {},
        {"version": "0.5.0", "installed": True, "enabled": True},
    ])

    def fake_run(*_args, **_kwargs):
        payload = next(responses)
        return type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps(payload),
            "stderr": "",
        })()

    monkeypatch.setattr("figure_tools.activation.subprocess.run", fake_run)
    adapter = CodexPluginAdapter(environment, codex=codex)

    installed = adapter.install(product, PRODUCT_VERSION)
    assert installed == PluginInstallation(True, True, PRODUCT_VERSION)
    assert not (stable / "old.txt").exists()
    assert (stable / ".agents" / "plugins" / "marketplace.json").is_file()

    adapter.restore("0.5.0")
    assert (stable / "old.txt").read_text(encoding="utf-8") == "old"


def test_update_cli_activates_a_verified_local_bundle(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    environment = _environment(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    codex = fake_bin / "codex"
    codex.write_text(
        "#!/bin/sh\n"
        "if [ \"$1 $2 $3\" = \"plugin marketplace list\" ]; then\n"
        "  printf '%s\\n' '{\"marketplaces\":[]}'\n"
        "elif [ \"$1 $2\" = \"plugin list\" ]; then\n"
        "  printf '%s\\n' '{\"installed\":[]}'\n"
        "elif [ \"$1 $2 $3\" = \"plugin marketplace add\" ]; then\n"
        "  printf '%s\\n' '{}'\n"
        "elif [ \"$1 $2\" = \"plugin add\" ]; then\n"
        f"  printf '%s\\n' '{{\"version\":\"{PRODUCT_VERSION}\","
        "\"installed\":true,\"enabled\":true}'\n"
        "else\n"
        "  printf '%s\\n' '{}'\n"
        "fi\n",
        encoding="utf-8",
    )
    codex.chmod(0o755)
    runtime_python = fake_bin / "runtime-python"
    runtime_python.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' "
        "'{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}' "
        "'{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"tools\":[{},{}]}}'\n",
        encoding="utf-8",
    )
    runtime_python.chmod(0o755)
    uv = fake_bin / "uv"
    uv.write_text(
        "#!/bin/sh\n"
        "runtime=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--directory\" ]; then shift; runtime=$1; fi\n"
        "  shift\n"
        "done\n"
        "mkdir -p \"$runtime/.venv/bin\"\n"
        "cp \"$FAKE_RUNTIME_PYTHON\" \"$runtime/.venv/bin/python\"\n"
        "chmod +x \"$runtime/.venv/bin/python\"\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
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
    monkeypatch.setenv("FAKE_RUNTIME_PYTHON", str(runtime_python))

    assert main([
        "update", "--bundle", str(_bundle(tmp_path)), "--codex", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["product_version"] == PRODUCT_VERSION
    assert payload["conclusion"] == "converged"
    assert Path(payload["active_runtime"]).is_dir()
