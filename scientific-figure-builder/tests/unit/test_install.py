"""Safe OpenCode configuration merger tests (plan section 14).

All tests use temp config files - the real opencode.json is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from figure_tools.config import deep_merge
from install.configure_opencode import apply_merge, propose_merge, render_diff

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
