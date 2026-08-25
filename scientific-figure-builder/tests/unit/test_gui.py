"""Offscreen smoke tests for the native configuration window."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox  # noqa: E402

from figure_tools.config_editor import GlobalConfigEditor  # noqa: E402
from figure_tools.connection_test import ConnectionTestService  # noqa: E402
from figure_tools.gui import ConfigurationWindow  # noqa: E402
from figure_tools.providers.auth import MemorySecretStore  # noqa: E402


@pytest.fixture
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_window_creation_page_switch_dirty_and_save(tmp_path: Path, app):
    editor = GlobalConfigEditor(tmp_path / "config.yaml")
    draft = editor.load()
    editor.set_provider(draft, "openai", {
        "type": "openai", "base_url": "https://models.example/v1",
        "key_env": "OPENAI_API_KEY", "supports_image_edit": True,
    })
    # The provider is a draft-only setup; the user still chooses free-text IDs.
    window = ConfigurationWindow(editor=editor, draft=draft)
    window.show()
    assert window.path_label.text().startswith("全局配置：")
    assert window.tabs.count() == 2
    window.tabs.setCurrentIndex(1)
    assert window.tabs.currentIndex() == 1
    window.tabs.setCurrentIndex(0)

    window.role_widgets["image_generate"]["provider"].setCurrentText("openai")
    window.role_widgets["image_generate"]["model"].setText("image-model")
    window.role_widgets["vision_analyze"]["provider"].setCurrentText("openai")
    window.role_widgets["vision_analyze"]["model"].setText("vision-model")
    window.role_widgets["vision_validate"]["provider"].setCurrentText("openai")
    window.role_widgets["vision_validate"]["model"].setText("validate-model")
    window.role_widgets["image_edit"]["inherit"].setChecked(True)  # type: ignore[attr-defined]
    assert "未保存" in window.dirty_label.text()
    assert window.save_draft() is True
    assert window.dirty_label.text() == "已保存"
    assert window.save_button.isEnabled() is False
    assert "image_edit" not in editor.load().models
    assert "image-model" in (tmp_path / "config.yaml").read_text(encoding="utf-8")
    window.close()


def test_inherited_edit_route_shows_capability_warning(tmp_path: Path, app):
    editor = GlobalConfigEditor(tmp_path / "config.yaml")
    draft = editor.load()
    editor.set_provider(draft, "openai", {
        "type": "openai", "base_url": "https://models.example/v1",
        "key_env": "OPENAI_API_KEY", "supports_image_edit": False,
    })
    window = ConfigurationWindow(editor=editor, draft=draft)
    window.role_widgets["image_generate"]["provider"].setCurrentText("openai")
    window.role_widgets["image_edit"]["inherit"].setChecked(True)  # type: ignore[attr-defined]
    assert "参考图编辑能力" in window.warning_label.text()
    window._set_dirty(False)
    window.close()


def test_unsaved_provider_type_is_reflected_in_compatibility_warning(tmp_path: Path, app):
    editor = GlobalConfigEditor(tmp_path / "config.yaml")
    draft = editor.load()
    editor.set_provider(draft, "shared", {
        "type": "openai", "base_url": "https://models.example/v1",
    })
    window = ConfigurationWindow(editor=editor, draft=draft)
    window.role_widgets["image_generate"]["provider"].setCurrentText("shared")
    window.provider_selector.setCurrentText("shared")
    window.provider_type.setCurrentText("anthropic")
    assert "不支持图像生成" in window.warning_label.text()
    window._set_dirty(False)
    window.close()


def test_provider_lifecycle_and_keyring_credential_save_from_empty_config(
    tmp_path: Path, app, monkeypatch,
):
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: QMessageBox.Ok)
    store = MemorySecretStore()
    editor = GlobalConfigEditor(tmp_path / "config.yaml", secret_store=store)
    window = ConfigurationWindow(editor=editor, draft=editor.load())
    assert window.add_provider("demo_provider") is True
    window.provider_base_url.setText("https://models.example/v1/responses")
    window.provider_key_env.setText("DEMO_API_KEY")
    window.provider_api_key.setText("demo-secret-value")
    assert window.provider_api_key.echoMode() == QLineEdit.EchoMode.Password
    window.role_widgets["image_generate"]["provider"].setCurrentText("demo_provider")
    window.role_widgets["image_generate"]["model"].setText("image-model")
    assert window.save_draft() is True
    draft = editor.load()
    credential_id = draft.providers["demo_provider"]["credential_id"]
    assert store.values[credential_id] == "demo-secret-value"
    assert draft.providers["demo_provider"]["base_url"] == "https://models.example/v1"
    assert window.provider_api_key.text() == ""

    assert window.rename_provider("renamed_provider") is True
    assert window.draft.models["image_generate"]["provider"] == "renamed_provider"
    assert window.role_widgets["image_generate"]["provider"].currentText() == "renamed_provider"
    assert window.delete_provider("renamed_provider", confirm=False) is False
    window.editor.remove_model(window.draft, "image_generate")
    assert window.delete_provider("renamed_provider", confirm=False) is True
    window._set_dirty(False)
    window.close()


def test_empty_api_key_preserves_existing_credential(tmp_path: Path, app):
    store = MemorySecretStore({"fixed-id": "existing-secret"})
    editor = GlobalConfigEditor(tmp_path / "config.yaml", secret_store=store)
    draft = editor.load()
    editor.set_provider(draft, "demo_provider", {
        "type": "openai", "base_url": "https://models.example/v1",
        "key_env": "DEMO_API_KEY", "credential_id": "fixed-id",
    })
    editor.save(draft)
    window = ConfigurationWindow(editor=editor, draft=editor.load())
    window.provider_selector.setCurrentText("demo_provider")
    assert window.provider_api_key.text() == ""
    assert window.save_draft() is True
    assert store.values == {"fixed-id": "existing-secret"}
    window.close()


def test_connection_test_runs_in_background_with_fake_transport(tmp_path: Path, app):
    calls = []

    class FakeTransport:
        def post(self, role, model, payload, image_paths=None):
            calls.append((role, model, image_paths))
            return {"checks": [], "blocking": False}

    store = MemorySecretStore()
    editor = GlobalConfigEditor(tmp_path / "config.yaml", secret_store=store)
    window = ConfigurationWindow(editor=editor, draft=editor.load())
    window.add_provider("demo_provider")
    window.provider_base_url.setText("https://models.example/v1")
    window.provider_key_env.setText("DEMO_API_KEY")
    window.role_widgets["vision_analyze"]["provider"].setCurrentText("demo_provider")
    window.role_widgets["vision_analyze"]["model"].setText("vision-model")
    window.provider_api_key.setText("temporary-key")
    window.connection_service_factory = lambda **kwargs: ConnectionTestService(
        transport_factory=lambda *_args, **_kwargs: FakeTransport()
    )
    assert window.test_connection() is True
    assert window.test_connection() is False
    for _ in range(50):
        app.processEvents()
        if window._connection_thread is None:
            break
    assert window._connection_thread is None
    assert calls and calls[0][0] == "reference_analysis"
    assert "连接成功" in window.credential_status_label.text()
    assert not (tmp_path / "config.yaml").exists()
    window._set_dirty(False)
    window.close()


def test_switching_provider_preserves_unsaved_provider_fields(tmp_path: Path, app):
    editor = GlobalConfigEditor(tmp_path / "config.yaml")
    window = ConfigurationWindow(editor=editor, draft=editor.load())
    window.add_provider("first_provider")
    window.add_provider("second_provider")
    window.provider_selector.setCurrentText("first_provider")
    window.provider_base_url.setText("https://first.example/v1")
    window.provider_api_key.setText("temporary-first")
    window.provider_selector.setCurrentText("second_provider")
    window.provider_selector.setCurrentText("first_provider")
    assert window.provider_base_url.text() == "https://first.example/v1"
    assert window.provider_api_key.text() == "temporary-first"
    window._set_dirty(False)
    window.close()


def test_saving_after_switch_persists_all_provider_drafts(tmp_path: Path, app):
    editor = GlobalConfigEditor(tmp_path / "config.yaml")
    window = ConfigurationWindow(editor=editor, draft=editor.load())
    window.add_provider("first_provider")
    window.add_provider("second_provider")
    window.provider_selector.setCurrentText("first_provider")
    window.provider_base_url.setText("https://first.example/v1")
    window.provider_selector.setCurrentText("second_provider")
    window.provider_base_url.setText("https://second.example/v1")
    assert window.save_draft() is True
    saved = editor.load().providers
    assert saved["first_provider"]["base_url"] == "https://first.example/v1"
    assert saved["second_provider"]["base_url"] == "https://second.example/v1"
    window.close()
