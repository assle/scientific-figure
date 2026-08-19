"""Tests for the Codex config.toml merger."""

from __future__ import annotations

from pathlib import Path

from install.configure_codex import (
    DEFAULT_MCP_NAME,
    codex_mcp_entry,
    update_codex_mcp_config,
    verify_codex_config,
)


def _entry(tmp_path: Path) -> dict:
    runtime = tmp_path / "runtime"
    python = runtime / ".venv" / "bin" / "python"
    return codex_mcp_entry(python, runtime)


def test_update_creates_codex_mcp_table(tmp_path: Path):
    config = tmp_path / "config.toml"
    entry = _entry(tmp_path)
    result = update_codex_mcp_config(config, DEFAULT_MCP_NAME, entry)
    assert result["applied"] is True
    assert result["backup"] is None

    text = config.read_text(encoding="utf-8")
    assert "[mcp_servers.scientific-figure]" in text
    assert 'command = "' in text
    assert "env_vars = [" in text
    for name in ("SCIENTIFIC_FIGURE_CONFIG", "ARK_AGENT_BASE_URL", "ARK_CODING_BASE_URL"):
        assert f'"{name}"' in text
    assert "[mcp_servers.scientific-figure.env]" not in text

    verified = verify_codex_config(config, DEFAULT_MCP_NAME)
    assert verified["checks"]["mcp_table"] is True
    assert verified["checks"]["command"] is True


def test_update_preserves_unrelated_config_and_env_subtable(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text(
        'model = "some-model"\n'
        "[mcp_servers.other]\n"
        'command = "other"\n'
        "[mcp_servers.scientific-figure.env]\n"
        'ARK_VISION_ANALYZE = "vision-model"\n',
        encoding="utf-8",
    )
    entry = _entry(tmp_path)
    update_codex_mcp_config(config, DEFAULT_MCP_NAME, entry, backup=True)

    text = config.read_text(encoding="utf-8")
    assert 'model = "some-model"' in text
    assert "[mcp_servers.other]" in text
    assert "[mcp_servers.scientific-figure.env]" in text
    assert 'ARK_VISION_ANALYZE = "vision-model"' in text
    assert "env_vars = [" not in text


def test_repeated_update_does_not_duplicate_table(tmp_path: Path):
    config = tmp_path / "config.toml"
    entry = _entry(tmp_path)
    update_codex_mcp_config(config, DEFAULT_MCP_NAME, entry)
    update_codex_mcp_config(config, DEFAULT_MCP_NAME, entry, backup=True)
    text = config.read_text(encoding="utf-8")
    assert text.count("[mcp_servers.scientific-figure]") == 1
