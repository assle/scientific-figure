"""Scope-aware uninstall and Keyring cleanup tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from figure_tools.install_transaction import InstallTransaction
from install.install_delivery import delivery_paths, launcher_text
from install.uninstall_delivery import build_parser, uninstall


def _layout(tmp_path: Path) -> dict[str, Path]:
    return {
        "config_home": tmp_path / "config",
        "data_home": tmp_path / "data",
        "install_home": tmp_path / "install",
        "state_home": tmp_path / "state",
        "cache_home": tmp_path / "cache",
        "session_home": tmp_path / "session",
        "codex_home": tmp_path / "codex",
        "bin_dir": tmp_path / "bin",
    }


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
    if paths.launcher_file is not None:
        paths.launcher_file.parent.mkdir(parents=True, exist_ok=True)
        paths.launcher_file.write_text(
            launcher_text(Path(sys.executable)), encoding="utf-8"
        )


def test_normal_uninstall_preserves_global_config_and_removes_own_launcher(tmp_path: Path):
    paths = delivery_paths(**_layout(tmp_path))
    _seed(paths, tmp_path)
    user_config = tmp_path / "config" / "scientific-figure-builder" / "config.yaml"
    user_config.parent.mkdir(parents=True)
    user_config.write_text("providers: {}\n", encoding="utf-8")
    result = uninstall(**_layout(tmp_path))
    assert not paths.runtime_scope_dir.exists()
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
    paths = delivery_paths(**_layout(tmp_path))
    _seed(paths, tmp_path)
    user_config = tmp_path / "config" / "scientific-figure-builder" / "config.yaml"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        "providers:\n  p: {credential_id: id-one}\n  q: {credential_id: id-two}\n",
        encoding="utf-8",
    )
    result = uninstall(**_layout(tmp_path), include_config=True)
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
    paths = delivery_paths(**_layout(tmp_path))
    _seed(paths, tmp_path)
    config_dir = tmp_path / "config" / "scientific-figure-builder"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(
        "providers:\n  p: {credential_id: id-one}\n", encoding="utf-8"
    )
    result = uninstall(**_layout(tmp_path), include_config=True)
    assert config_dir.exists()
    assert any("retained" in warning for warning in result["warnings"])


def test_unreadable_global_config_is_retained_for_safety(tmp_path: Path, monkeypatch):
    class FakeKeyring:
        @staticmethod
        def delete_password(*_args):
            raise AssertionError("must not delete with unreadable config")

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    paths = delivery_paths(**_layout(tmp_path))
    _seed(paths, tmp_path)
    config_dir = tmp_path / "config" / "scientific-figure-builder"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("providers: [broken", encoding="utf-8")
    result = uninstall(**_layout(tmp_path), include_config=True)
    assert config_dir.exists()
    assert any("could not be read" in warning for warning in result["warnings"])


def test_project_uninstall_removes_only_its_versioned_runtime(tmp_path: Path):
    layout = _layout(tmp_path)
    global_paths = delivery_paths(**layout)
    project_a_dir = tmp_path / "project-a"
    project_b_dir = tmp_path / "project-b"
    project_a = delivery_paths(**layout, project_dir=project_a_dir)
    project_b = delivery_paths(**layout, project_dir=project_b_dir)
    for paths in (global_paths, project_a, project_b):
        paths.runtime_dir.mkdir(parents=True)

    uninstall(**layout, project_dir=project_a_dir)

    assert not project_a.runtime_scope_dir.exists()
    assert global_paths.runtime_dir.is_dir()
    assert project_b.runtime_dir.is_dir()


@pytest.mark.parametrize("target", ["runtime", "opencode", "codex"])
def test_targeted_uninstall_preserves_unselected_products(
    tmp_path: Path, target: str,
):
    layout = _layout(tmp_path)
    paths = delivery_paths(**layout)
    _seed(paths, tmp_path)
    uninstall(
        **layout,
        remove_runtime=target == "runtime",
        remove_opencode=target == "opencode",
        remove_codex=target == "codex",
    )
    assert paths.runtime_scope_dir.exists() is (target != "runtime")
    assert paths.skill_dir.exists() is (target != "opencode")
    assert paths.command_file.exists() is (target != "opencode")
    opencode_config = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert ("scientific-figure" in opencode_config["mcp"]) is (target != "opencode")
    assert paths.codex_skill_dir.exists() is (target != "codex")
    codex_text = paths.codex_config_file.read_text(encoding="utf-8")
    assert ("[mcp_servers.scientific-figure]" in codex_text) is (target != "codex")


def test_uninstall_cli_targets_are_explicit():
    parser = build_parser()
    assert parser.parse_args([]).target == "runtime"
    assert parser.parse_args(["--opencode"]).target == "opencode"
    assert parser.parse_args(["--codex-legacy"]).target == "codex"
    assert parser.parse_args(["--integrations"]).target == "integrations"
    assert parser.parse_args(["--all"]).target == "all"


def test_uninstall_recognizes_active_install_lock(tmp_path: Path):
    layout = _layout(tmp_path)
    paths = delivery_paths(**layout)
    paths.runtime_dir.mkdir(parents=True)
    with InstallTransaction(paths) as transaction:
        result = uninstall(
            **layout,
            remove_runtime=True,
            remove_opencode=False,
            remove_codex=False,
        )
        assert paths.runtime_dir.is_dir()
        assert any("install is active" in warning for warning in result["warnings"])
        transaction.commit()


def test_uninstall_cleans_orphaned_install_state(tmp_path: Path):
    layout = _layout(tmp_path)
    paths = delivery_paths(**layout)
    paths.runtime_dir.mkdir(parents=True)
    paths.install_lock_dir.mkdir(parents=True)
    (paths.install_lock_dir / "owner.json").write_text(
        json.dumps({"pid": 999999999}), encoding="utf-8"
    )
    (paths.staging_parent / "orphan").mkdir(parents=True)
    (paths.transaction_backup_parent / "orphan").mkdir(parents=True)
    result = uninstall(
        **layout,
        remove_runtime=True,
        remove_opencode=False,
        remove_codex=False,
    )
    assert not paths.runtime_scope_dir.exists()
    assert not paths.install_lock_dir.exists()
    assert str(paths.install_lock_dir) in result["removed"]


def test_opencode_uninstall_preserves_jsonc_comments_and_other_servers(tmp_path: Path):
    layout = _layout(tmp_path)
    opencode_home = layout["config_home"] / "opencode"
    config = opencode_home / "opencode.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text(
        """{
  // keep top
  "mcp": {
    "other": {"command": ["other"]}, // keep inline
    "scientific-figure": {"command": ["scientific"]},
  },
  /* keep permission */
  "permission": {"bash": "ask"},
}
""",
        encoding="utf-8",
    )
    uninstall(
        **layout,
        remove_runtime=False,
        remove_opencode=True,
        remove_codex=False,
    )
    candidate = config.read_text(encoding="utf-8")
    assert "scientific-figure" not in candidate
    assert '"other": {"command": ["other"]}, // keep inline' in candidate
    assert "// keep top" in candidate
    assert "// keep inline" in candidate
    assert "/* keep permission */" in candidate
    assert '"permission": {"bash": "ask"},' in candidate
