"""Scope-aware uninstall and Keyring cleanup tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from install.install_delivery import delivery_paths, launcher_text
from install.uninstall_delivery import uninstall


def _seed(paths, tmp_path: Path):
    paths.runtime_dir.mkdir(parents=True)
    (paths.runtime_dir / "figure_tools").mkdir()
    paths.skill_dir.mkdir(parents=True)
    paths.command_file.parent.mkdir(parents=True)
    paths.command_file.write_text("command", encoding="utf-8")
    paths.codex_skill_dir.mkdir(parents=True)
    paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text(json.dumps({"mcp": {"scientific-figure": {}}}), encoding="utf-8")
    paths.codex_config_file.parent.mkdir(parents=True, exist_ok=True)
    paths.codex_config_file.write_text("[mcp_servers.scientific-figure]\ncommand = 'x'\n", encoding="utf-8")
    assert paths.launcher_file is not None
    paths.launcher_file.parent.mkdir(parents=True, exist_ok=True)
    paths.launcher_file.write_text(launcher_text(Path(sys.executable)), encoding="utf-8")


def test_normal_uninstall_preserves_global_config_and_removes_own_launcher(tmp_path: Path):
    paths = delivery_paths(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    _seed(paths, tmp_path)
    user_config = tmp_path / "config" / "scientific-figure-builder" / "config.yaml"
    user_config.parent.mkdir(parents=True)
    user_config.write_text("providers: {}\n", encoding="utf-8")
    result = uninstall(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    assert not paths.runtime_dir.exists()
    assert not paths.launcher_file.exists()
    assert user_config.exists()
    assert not result["warnings"]


def test_config_uninstall_deletes_only_configured_keyring_ids(tmp_path: Path, monkeypatch):
    calls = []

    class FakeKeyring:
        @staticmethod
        def delete_password(service, username):
            calls.append((service, username))

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    paths = delivery_paths(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    _seed(paths, tmp_path)
    user_config = tmp_path / "config" / "scientific-figure-builder" / "config.yaml"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        "providers:\n  p: {credential_id: id-one}\n  q: {credential_id: id-two}\n",
        encoding="utf-8",
    )
    result = uninstall(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", include_config=True, bin_dir=tmp_path / "bin",
    )
    assert calls == [("scientific-figure-builder", "id-one"),
                     ("scientific-figure-builder", "id-two")]
    assert not user_config.parent.exists()
    assert not result["warnings"]


def test_keyring_failure_retains_user_config(tmp_path: Path, monkeypatch):
    class BrokenKeyring:
        @staticmethod
        def delete_password(*_args):
            raise RuntimeError("locked")

    monkeypatch.setitem(sys.modules, "keyring", BrokenKeyring)
    paths = delivery_paths(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    _seed(paths, tmp_path)
    config_dir = tmp_path / "config" / "scientific-figure-builder"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(
        "providers:\n  p: {credential_id: id-one}\n", encoding="utf-8"
    )
    result = uninstall(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", include_config=True, bin_dir=tmp_path / "bin",
    )
    assert config_dir.exists()
    assert any("retained" in warning for warning in result["warnings"])


def test_unreadable_global_config_is_retained_for_safety(tmp_path: Path, monkeypatch):
    class FakeKeyring:
        @staticmethod
        def delete_password(*_args):
            raise AssertionError("must not delete with unreadable config")

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    paths = delivery_paths(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", bin_dir=tmp_path / "bin",
    )
    _seed(paths, tmp_path)
    config_dir = tmp_path / "config" / "scientific-figure-builder"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("providers: [broken", encoding="utf-8")
    result = uninstall(
        config_home=tmp_path / "config", data_home=tmp_path / "data",
        codex_home=tmp_path / "codex", include_config=True, bin_dir=tmp_path / "bin",
    )
    assert config_dir.exists()
    assert any("could not be read" in warning for warning in result["warnings"])
