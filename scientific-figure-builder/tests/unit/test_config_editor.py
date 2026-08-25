"""Global configuration editing seams (issue 11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from figure_tools.config_editor import (
    ConfigConflictError,
    GlobalConfigEditor,
    ProviderInUseError,
)
from figure_tools.providers.auth import MemorySecretStore


def _editor(path: Path, store=None) -> GlobalConfigEditor:
    return GlobalConfigEditor(path, secret_store=store)


def test_missing_file_loads_empty_draft_without_creating_parent(tmp_path: Path):
    path = tmp_path / "nested" / "config.yaml"
    draft = _editor(path).load()
    assert draft.exists is False
    assert draft.models == {}
    assert draft.providers == {}
    assert not path.parent.exists()


def test_save_preserves_comments_unknown_fields_and_order(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "# keep this header\n"
        "schema_version: '1.0'\n"
        "other:\n  keep: true\n"
        "models:\n  generate: {model: old, provider: p, extra: keep}\n"
        "providers:\n  p: {type: openai, base_url: https://old, unknown: x}\n",
        encoding="utf-8",
    )
    editor = _editor(path)
    draft = editor.load()
    editor.set_model(draft, "generate", {"model": "new"})
    editor.set_provider(draft, "p", {"base_url": "https://new"})
    editor.save(draft)
    blob = path.read_text(encoding="utf-8")
    assert "# keep this header" in blob
    assert "other:" in blob and "keep: true" in blob
    assert "extra: keep" in blob and "unknown: x" in blob
    assert "model: new" in blob and "base_url: https://new" in blob


def test_rename_provider_updates_routes_and_delete_rejects_references(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "models:\n  a: {model: m, provider: old}\n"
        "providers:\n  old: {type: openai, credential_id: cred}\n",
        encoding="utf-8",
    )
    editor = _editor(path)
    draft = editor.load()
    editor.rename_provider(draft, "old", "new")
    assert draft.providers["new"]["credential_id"] == "cred"
    assert draft.models["a"]["provider"] == "new"
    with pytest.raises(ProviderInUseError):
        editor.delete_provider(draft, "new")
    editor.delete_provider(draft, "new", force=True)


def test_external_change_is_detected_even_when_file_was_initially_missing(tmp_path: Path):
    path = tmp_path / "config.yaml"
    editor = _editor(path)
    draft = editor.load()
    draft.models["a"] = {"model": "m"}
    path.write_text("external: true\n", encoding="utf-8")
    with pytest.raises(ConfigConflictError):
        editor.save(draft)


def test_credentials_are_prepared_before_yaml_and_old_credential_cleaned_last(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  p: {type: openai, credential_id: old-id}\n", encoding="utf-8"
    )
    store = MemorySecretStore({"old-id": "old-secret"})
    editor = _editor(path, store)
    draft = editor.load()
    editor.set_credential(draft, "p", "new-secret", credential_id="new-id")
    editor.save(draft)
    assert store.values == {"new-id": "new-secret"}
    assert [operation for operation, _ in store.operations] == [
        "get", "set", "delete",
    ]
    assert "new-secret" not in path.read_text(encoding="utf-8")
    assert path.with_name("config.yaml.bak").is_file()


def test_legacy_protocol_is_migrated_on_read_with_warning(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  legacy: {protocol: responses, base_url: https://example}\n",
        encoding="utf-8",
    )
    with pytest.warns(FutureWarning, match="use type: openai"):
        draft = _editor(path).load()
    assert draft.providers["legacy"]["type"] == "openai"
    assert "protocol" not in draft.providers["legacy"]


def test_save_requires_secure_store_for_new_credentials(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("providers:\n  p: {type: openai}\n", encoding="utf-8")
    editor = _editor(path)
    draft = editor.load()
    editor.set_credential(draft, "p", "secret")
    with pytest.raises(Exception, match="secure system credential"):
        editor.save(draft)
    assert "secret" not in path.read_text(encoding="utf-8")


def test_existing_file_mode_is_preserved_and_snapshot_scrubs_secret_keys(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  p: {type: openai, api_key: should-not-be-saved}\n",
        encoding="utf-8",
    )
    path.chmod(0o640)
    editor = _editor(path)
    draft = editor.load()
    assert "api_key" not in str(draft.public_snapshot())
    with pytest.raises(Exception, match="secure system store"):
        editor.save(draft)
