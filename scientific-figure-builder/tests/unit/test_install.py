"""Safe OpenCode configuration merger tests (plan section 14).

All tests use temp config files - the real opencode.json is never touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from figure_tools.config import deep_merge
from install.configure_opencode import apply_merge, propose_merge, render_diff
from install.install_delivery import (
    delivery_paths,
    install_delivery,
    verify_delivery,
)

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
    global_paths = delivery_paths(config_home=config_home, data_home=data_home)
    assert global_paths.skill_dir == (
        config_home / "opencode" / "skills" / "scientific-figure-builder"
    )
    assert global_paths.config_file == config_home / "opencode" / "opencode.json"

    project = tmp_path / "project"
    project.mkdir()
    project_paths = delivery_paths(
        config_home=config_home,
        data_home=data_home,
        project_dir=project,
    )
    assert project_paths.skill_dir == (
        project / ".opencode" / "skills" / "scientific-figure-builder"
    )
    assert project_paths.config_file == project / "opencode.json"


def test_delivery_paths_use_existing_jsonc_config(tmp_path: Path):
    config_home = tmp_path / "config"
    opencode_home = config_home / "opencode"
    opencode_home.mkdir(parents=True)
    jsonc = opencode_home / "opencode.jsonc"
    jsonc.write_text("{}\n", encoding="utf-8")
    paths = delivery_paths(config_home=config_home, data_home=tmp_path / "data")
    assert paths.config_file == jsonc


def test_project_delivery_paths_use_existing_dot_opencode_config(tmp_path: Path):
    project = tmp_path / "project"
    nested_config = project / ".opencode" / "opencode.json"
    nested_config.parent.mkdir(parents=True)
    nested_config.write_text("{}\n", encoding="utf-8")
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        project_dir=project,
    )
    assert paths.config_file == nested_config


def test_install_delivery_is_discoverable_and_preserves_config(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text(json.dumps(_existing_config()), encoding="utf-8")

    def _use_test_python(runtime_dir: Path, *, with_ark: bool) -> Path:
        assert (runtime_dir / "figure_tools" / "server.py").is_file()
        assert with_ark is False
        return Path(sys.executable)

    result = install_delivery(
        source,
        paths,
        with_ark=False,
        runtime_sync=_use_test_python,
    )
    assert (paths.skill_dir / "SKILL.md").is_file()
    assert (paths.skill_dir / "references" / "routing-rules.md").is_file()
    assert paths.command_file.is_file()
    assert result["mcp_tools"] == 14

    merged = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert merged["provider"] == _existing_config()["provider"]
    assert merged["mcp"]["other-server"] == _existing_config()["mcp"]["other-server"]
    assert merged["mcp"]["scientific-figure"]["command"][0] == str(
        Path(sys.executable).absolute()
    )

    verified = verify_delivery(paths)
    assert verified["mcp_tools"] == 14


def test_install_delivery_can_be_repeated_safely(tmp_path: Path):
    source = Path(__file__).resolve().parents[2]
    paths = delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
    )

    def _use_test_python(_runtime_dir: Path, *, with_ark: bool) -> Path:
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
