"""Offscreen smoke tests for the native configuration window."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from figure_tools.config_editor import GlobalConfigEditor  # noqa: E402
from figure_tools.gui import ConfigurationWindow  # noqa: E402


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
