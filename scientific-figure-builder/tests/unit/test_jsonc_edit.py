"""Comment-preserving JSONC edits for OpenCode MCP configuration."""

from __future__ import annotations

import json

import pytest

from figure_tools.jsonc_edit import load_jsonc, remove_mcp_entry, set_mcp_entry


ENTRY = {
    "type": "local",
    "command": ["/runtime/python", "-m", "figure_tools.server"],
    "enabled": True,
}

JSONC = """{
  // top-level guidance
  "$schema": "https://opencode.ai/config.json", // schema note
  "provider": {"custom": {"url": "https://example.test//v1"}},
  /* keep this provider-to-MCP explanation */
  "mcp": {
    // unrelated server
    "other": {"type": "local", "command": ["other"]}, // keep inline
  },
  "permission": {"bash": "ask"},
}
"""


def test_load_jsonc_supports_all_comment_forms_and_trailing_commas() -> None:
    data = load_jsonc(JSONC)
    assert data["provider"]["custom"]["url"] == "https://example.test//v1"
    assert data["mcp"]["other"]["command"] == ["other"]


def test_set_mcp_entry_preserves_unrelated_text_exactly() -> None:
    candidate = set_mcp_entry(JSONC, "scientific-figure", ENTRY)
    for exact in (
        "// top-level guidance",
        '"$schema": "https://opencode.ai/config.json", // schema note',
        '"provider": {"custom": {"url": "https://example.test//v1"}}',
        "/* keep this provider-to-MCP explanation */",
        '// unrelated server\n    "other": {"type": "local", "command": ["other"]}, // keep inline',
        '"permission": {"bash": "ask"},',
    ):
        assert exact in candidate
    assert load_jsonc(candidate)["mcp"]["scientific-figure"] == ENTRY


def test_repeated_set_is_idempotent_and_does_not_duplicate_key() -> None:
    first = set_mcp_entry(JSONC, "scientific-figure", ENTRY)
    second = set_mcp_entry(first, "scientific-figure", ENTRY)
    assert second == first
    assert second.count('"scientific-figure"') == 1


def test_existing_target_value_is_replaced_without_reformatting_siblings() -> None:
    first = set_mcp_entry(JSONC, "scientific-figure", {"command": ["old"]})
    second = set_mcp_entry(first, "scientific-figure", ENTRY)
    assert '"other": {"type": "local", "command": ["other"]}' in second
    assert "// keep inline" in second
    assert load_jsonc(second)["mcp"]["scientific-figure"] == ENTRY


def test_remove_only_target_entry_and_preserves_comments() -> None:
    installed = set_mcp_entry(JSONC, "scientific-figure", ENTRY)
    candidate, changed = remove_mcp_entry(installed, "scientific-figure")
    assert changed is True
    assert "scientific-figure" not in load_jsonc(candidate)["mcp"]
    assert load_jsonc(candidate)["mcp"]["other"]["command"] == ["other"]
    assert "// unrelated server" in candidate
    assert '"other": {"type": "local", "command": ["other"]}, // keep inline' in candidate
    assert "/* keep this provider-to-MCP explanation */" in candidate


def test_empty_and_plain_json_documents_are_supported() -> None:
    empty = set_mcp_entry("", "scientific-figure", ENTRY)
    plain = set_mcp_entry('{"provider": {}}\n', "scientific-figure", ENTRY)
    assert load_jsonc(empty)["mcp"]["scientific-figure"] == ENTRY
    assert load_jsonc(plain)["provider"] == {}
    assert load_jsonc(plain)["mcp"]["scientific-figure"] == ENTRY


def test_remove_missing_target_is_a_noop() -> None:
    candidate, changed = remove_mcp_entry(JSONC, "scientific-figure")
    assert changed is False
    assert candidate == JSONC


@pytest.mark.parametrize(
    "text",
    [
        '{"mcp": [}',
        '{"mcp": {/* unterminated}',
        '{"mcp" {}}',
    ],
)
def test_invalid_jsonc_is_rejected(text: str) -> None:
    with pytest.raises((ValueError, json.JSONDecodeError)):
        load_jsonc(text)


def test_non_object_mcp_is_rejected_before_edit() -> None:
    with pytest.raises(ValueError, match="field 'mcp' must be an object"):
        set_mcp_entry('{"mcp": []}', "scientific-figure", ENTRY)


def test_duplicate_object_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate JSONC object key"):
        load_jsonc('{"mcp": {}, "mcp": {}}')
