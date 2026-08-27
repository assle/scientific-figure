"""Qt Quick controller and packaged-view tests."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from figure_tools.config_editor import GlobalConfigEditor  # noqa: E402
from figure_tools.providers.auth import MemorySecretStore  # noqa: E402
from figure_tools.qml_controller import GuiController  # noqa: E402


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _controller(tmp_path: Path):
    store = MemorySecretStore()
    editor = GlobalConfigEditor(tmp_path / "config.yaml", secret_store=store)
    return GuiController(editor=editor, draft=editor.load()), editor, store


def test_qml_controller_saves_routes_providers_and_keyring(tmp_path: Path, app):
    controller, editor, store = _controller(tmp_path)
    assert controller.addProvider("demo_provider") is True
    controller.updateProvider("base_url", "https://models.example/v1/responses")
    controller.updateProvider("key_env", "DEMO_API_KEY")
    controller.updateProvider("api_key", "temporary-secret")
    controller.updateProviderBool("supports_image_edit", True)
    controller.updateRole("vision_analyze", "provider", "demo_provider")
    controller.updateRole("vision_analyze", "model", "vision-model")
    assert controller.dirty is True
    assert controller.save() is True

    draft = editor.load()
    provider = draft.providers["demo_provider"]
    assert provider["base_url"] == "https://models.example/v1"
    assert provider["supports_image_edit"] is True
    assert draft.models["vision_analyze"]["model"] == "vision-model"
    assert store.values[provider["credential_id"]] == "temporary-secret"
    assert controller.dirty is False


def test_qml_controller_updates_references_on_rename(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    controller.addProvider("first_provider")
    controller.updateRole("image_generate", "provider", "first_provider")
    controller.updateRole("image_generate", "model", "image-model")
    assert controller.renameSelectedProvider("renamed_provider") is True
    role = next(item for item in controller.roles if item["role"] == "image_generate")
    assert role["provider"] == "renamed_provider"
    assert controller.deleteSelectedProvider() is False
    assert "引用" in controller.notification


def test_packaged_qml_loads_offscreen(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appController", controller)
    qml_path = files("figure_tools.resources").joinpath("qml/Main.qml")
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    assert len(engine.rootObjects()) == 1
    root = engine.rootObjects()[0]
    assert root.objectName() == "qmlRoot"
    assert root.findChild(QObject, "sidebar") is not None
    assert root.findChild(QObject, "saveButton") is not None
    root.setProperty("visible", False)


def test_gui_entrypoint_uses_qml(monkeypatch):
    import figure_tools.gui as gui
    import figure_tools.qml_gui as qml_gui

    calls = []
    monkeypatch.setattr(qml_gui, "run_qml_gui", lambda argv=None: calls.append(argv) or 0)
    assert gui.run_gui(["--manual-test"]) == 0
    assert calls == [["--manual-test"]]


def test_same_value_updates_do_not_mark_draft_dirty(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    controller.addProvider("demo_provider")
    controller.updateRole("vision_analyze", "provider", "demo_provider")
    controller.updateRole("vision_analyze", "model", "vision-model")
    assert controller.save() is True
    assert controller.dirty is False
    role = next(item for item in controller.roles if item["role"] == "vision_analyze")
    provider = controller.selectedProvider
    controller.updateRole("vision_analyze", "provider", role["provider"])
    controller.updateRole("vision_analyze", "model", role["model"])
    controller.updateProvider("base_url", provider["base_url"])
    controller.updateProviderBool(
        "supports_image_edit", provider["supports_image_edit"]
    )
    assert controller.dirty is False


def test_qml_separates_provider_and_credential_pages(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appController", controller)
    qml_path = files("figure_tools.resources").joinpath("qml/Main.qml")
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    root = engine.rootObjects()[0]
    providers_page = root.findChild(QObject, "providersPage")
    credentials_page = root.findChild(QObject, "credentialsPage")
    assert providers_page is not None
    assert credentials_page is not None
    assert providers_page is not credentials_page
    assert root.findChild(QObject, "emptyProviderAction") is not None
    assert root.property("providerSelectionAvailable") is False
    assert root.findChild(QObject, "emptyProviderRouteAction") is not None
    root.setProperty("visible", False)
