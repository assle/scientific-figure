"""Qt Quick controller and packaged-view tests."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl  # noqa: E402
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


def _load_qml(controller: GuiController):
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appController", controller)
    qml_path = files("figure_tools.resources").joinpath("qml/Main.qml")
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    return engine, engine.rootObjects()[0]


def _activate_provider_type(root: QObject, provider_type: str) -> None:
    selector = root.findChild(QObject, "providerTypeSelector")
    index = {"openai": 0, "anthropic": 1, "dashscope": 2}[provider_type]
    assert selector.setProperty("currentIndex", index)
    assert QMetaObject.invokeMethod(
        selector,
        "activated",
        Qt.ConnectionType.DirectConnection,
        Q_ARG(int, index),
    )


def test_qml_controller_saves_routes_providers_and_keyring(tmp_path: Path, app):
    controller, editor, store = _controller(tmp_path)
    assert controller.addProvider("demo_provider") is True
    controller.updateProvider("base_url", "https://models.example/v1/responses")
    controller.updateProvider("key_env", "DEMO_API_KEY")
    controller.updateProvider("api_key", "temporary-secret")
    controller.updateProviderBool("supports_image_edit", True)
    controller.updateProviderBool("supports_reference_image", True)
    controller.updateProviderBool("supports_mask_edit", True)
    controller.updateRole("vision_analyze", "provider", "demo_provider")
    controller.updateRole("vision_analyze", "model", "vision-model")
    assert controller.dirty is True
    assert controller.save() is True

    draft = editor.load()
    provider = draft.providers["demo_provider"]
    assert provider["base_url"] == "https://models.example/v1"
    assert provider["supports_image_edit"] is True
    assert provider["supports_reference_image"] is True
    assert provider["supports_mask_edit"] is True
    assert draft.models["vision_analyze"]["model"] == "vision-model"
    assert store.values[provider["credential_id"]] == "temporary-secret"
    assert controller.dirty is False


def test_qml_controller_saves_only_openai_provider_fields(tmp_path: Path, app):
    controller, editor, _store = _controller(tmp_path)
    assert controller.addProvider("openai_provider") is True
    controller.updateProvider("auth_scheme", "bearer")
    controller.updateProvider("messages_path", "/v1/messages")
    controller.updateProvider("anthropic_version", "2024-01-01")
    controller.updateProviderBool("supports_image_edit", True)

    assert controller.save() is True

    provider = editor.load().providers["openai_provider"]
    assert provider["type"] == "openai"
    assert provider["supports_image_edit"] is True
    assert "auth_scheme" not in provider
    assert "messages_path" not in provider
    assert "anthropic_version" not in provider


def test_qml_controller_saves_only_anthropic_provider_fields(tmp_path: Path, app):
    controller, editor, _store = _controller(tmp_path)
    assert controller.addProvider("anthropic_provider") is True
    controller.updateProvider("type", "anthropic")
    controller.updateProvider("auth_scheme", "bearer")
    controller.updateProvider("messages_path", "/v1/messages")
    controller.updateProvider("anthropic_version", "2024-01-01")
    controller.updateProviderBool("supports_image_edit", True)

    assert controller.save() is True

    provider = editor.load().providers["anthropic_provider"]
    assert provider["type"] == "anthropic"
    assert provider["auth_scheme"] == "bearer"
    assert provider["messages_path"] == "/v1/messages"
    assert provider["anthropic_version"] == "2024-01-01"
    assert "supports_image_edit" not in provider


def test_qml_controller_saves_dashscope_native_provider(tmp_path: Path, app):
    controller, editor, _store = _controller(tmp_path)
    assert controller.addProvider("dashscope_images") is True
    controller.updateProvider("type", "dashscope")
    controller.updateProvider(
        "base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    controller.updateProvider("key_env", "DASHSCOPE_API_KEY")
    controller.updateProviderBool("supports_image_edit", True)
    controller.updateProviderBool("supports_reference_image", True)
    controller.updateProviderBool("supports_multi_reference", True)
    controller.updateProviderBool("supports_seed", True)
    controller.updateProviderBool("supports_candidate_batch", True)

    assert controller.save() is True

    provider = editor.load().providers["dashscope_images"]
    assert provider["type"] == "dashscope"
    assert provider["base_url"] == "https://dashscope.aliyuncs.com/api/v1"
    assert provider["supports_image_edit"] is True
    assert provider["supports_multi_reference"] is True


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
    import figure_tools.qml_gui as qml_gui
    from figure_tools.__main__ import main

    calls = []
    monkeypatch.setattr(qml_gui, "run_gui", lambda argv=None: calls.append(argv) or 0)
    assert main(["gui", "--manual-test"]) == 0
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


def test_qml_provider_advanced_fields_have_persistent_guidance(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    engine, root = _load_qml(controller)

    advanced_hint = root.findChild(QObject, "providerAdvancedHint")
    messages_path_label = root.findChild(QObject, "providerMessagesPathLabel")
    anthropic_version_label = root.findChild(
        QObject, "providerAnthropicVersionLabel"
    )

    assert "仅在接口文档" in advanced_hint.property("text")
    assert messages_path_label.property("text") == "Messages Path"
    assert anthropic_version_label.property("text") == "Anthropic Version"
    root.setProperty("visible", False)


def test_qml_switches_from_openai_to_anthropic_provider_fields(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    assert controller.addProvider("demo_provider") is True
    controller.setPage("providers")
    engine, root = _load_qml(controller)
    anthropic_settings = root.findChild(QObject, "anthropicAdvancedSettings")
    openai_capabilities = root.findChild(QObject, "openaiCapabilities")

    assert anthropic_settings is not None
    assert openai_capabilities is not None
    assert anthropic_settings.property("visible") is False
    assert openai_capabilities.property("visible") is True

    _activate_provider_type(root, "anthropic")
    app.processEvents()

    assert anthropic_settings.property("visible") is True
    assert openai_capabilities.property("visible") is False
    root.setProperty("visible", False)
    del engine


def test_qml_switches_from_anthropic_to_openai_provider_fields(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    assert controller.addProvider("demo_provider") is True
    controller.updateProvider("type", "anthropic")
    controller.setPage("providers")
    engine, root = _load_qml(controller)
    anthropic_settings = root.findChild(QObject, "anthropicAdvancedSettings")
    openai_capabilities = root.findChild(QObject, "openaiCapabilities")

    assert anthropic_settings.property("visible") is True
    assert openai_capabilities.property("visible") is False

    _activate_provider_type(root, "openai")
    app.processEvents()

    assert anthropic_settings.property("visible") is False
    assert openai_capabilities.property("visible") is True
    root.setProperty("visible", False)
    del engine


def test_qml_switches_to_dashscope_image_provider_fields(tmp_path: Path, app):
    controller, _editor, _store = _controller(tmp_path)
    assert controller.addProvider("demo_provider") is True
    controller.setPage("providers")
    engine, root = _load_qml(controller)

    _activate_provider_type(root, "dashscope")
    app.processEvents()

    assert controller.selectedProvider["type"] == "dashscope"
    assert root.findChild(QObject, "anthropicAdvancedSettings").property(
        "visible"
    ) is False
    assert root.findChild(QObject, "openaiCapabilities").property(
        "visible"
    ) is True
    root.setProperty("visible", False)
    del engine


@pytest.mark.parametrize(
    ("provider_type", "anthropic_visible", "openai_visible"),
    [
        ("openai", False, True),
        ("anthropic", True, False),
        ("dashscope", False, True),
    ],
)
def test_qml_reopens_with_fields_for_saved_provider_type(
    tmp_path: Path,
    app,
    provider_type: str,
    anthropic_visible: bool,
    openai_visible: bool,
):
    controller, editor, _store = _controller(tmp_path)
    assert controller.addProvider("saved_provider") is True
    controller.updateProvider("type", provider_type)
    assert controller.save() is True

    reopened = GuiController(editor=editor, draft=editor.load())
    reopened.setPage("providers")
    engine, root = _load_qml(reopened)

    assert root.findChild(QObject, "anthropicAdvancedSettings").property(
        "visible"
    ) is anthropic_visible
    assert root.findChild(QObject, "openaiCapabilities").property(
        "visible"
    ) is openai_visible
    root.setProperty("visible", False)
    del engine
