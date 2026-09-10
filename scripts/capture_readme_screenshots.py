"""Render the README configuration-app screenshots from the packaged QML."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPOSITORY_DIR = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPOSITORY_DIR / "scientific-figure-builder"
sys.path.insert(0, str(PACKAGE_DIR))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from figure_tools.config_editor import GlobalConfigEditor
from figure_tools.providers.auth import MemorySecretStore
from figure_tools.qml_controller import GuiController
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

PAGE_SIZES = {
    "models": (1120, 763),
    "providers": (1120, 900),
    "credentials": (1120, 860),
}
DEMO_CREDENTIAL_ID = "10000000-0000-4000-8000-000000000001"


def _add_provider(
    controller: GuiController,
    provider_id: str,
    provider_type: str,
    base_url: str,
    key_env: str,
) -> None:
    if not controller.addProvider(provider_id):
        raise RuntimeError(f"could not add demo Provider: {provider_id}")
    controller.updateProvider("type", provider_type)
    controller.updateProvider("base_url", base_url)
    controller.updateProvider("key_env", key_env)


def _seed_demo_configuration(
    controller: GuiController,
) -> None:
    _add_provider(
        controller,
        "openai_vision",
        "openai",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
    )
    controller.updateProvider("api_key", "demo-secret")
    for field in (
        "supports_image_edit",
        "supports_reference_image",
        "supports_multi_reference",
        "supports_mask_edit",
        "supports_structure_control",
        "supports_native_alpha",
        "supports_seed",
        "supports_candidate_batch",
    ):
        controller.updateProviderBool(field, True)

    _add_provider(
        controller,
        "anthropic_reasoning",
        "anthropic",
        "https://api.anthropic.com/v1",
        "ANTHROPIC_API_KEY",
    )
    controller.updateProvider("auth_scheme", "x-api-key")
    controller.updateProvider("messages_path", "/messages")
    controller.updateProvider("anthropic_version", "2023-06-01")

    _add_provider(
        controller,
        "dashscope_images",
        "dashscope",
        "https://dashscope.aliyuncs.com/api/v1",
        "DASHSCOPE_API_KEY",
    )
    controller.updateProviderBool("supports_image_edit", True)
    controller.updateProviderBool("supports_reference_image", True)
    controller.updateProviderBool("supports_multi_reference", True)
    controller.updateProviderBool("supports_seed", True)
    controller.updateProviderBool("supports_candidate_batch", True)

    routes = {
        "phase_reasoning": ("anthropic_reasoning", "claude-sonnet-4-5"),
        "vision_analyze": ("openai_vision", "gpt-5-vision"),
        "image_generate": ("dashscope_images", "qwen-image-3.0"),
        "vision_validate": ("openai_vision", "gpt-5-vision"),
    }
    for role, (provider_id, model_id) in routes.items():
        controller.updateRole(role, "provider", provider_id)
        controller.updateRole(role, "model", model_id)
    controller.setRoleInheritance("image_edit", True)

    with patch(
        "figure_tools.config_editor.new_credential_id",
        return_value=DEMO_CREDENTIAL_ID,
    ):
        if not controller.save():
            raise RuntimeError("could not save the demo configuration")
    controller._notification = ""
    controller.notificationChanged.emit()
    controller.draft.path = (
        Path.home() / ".config" / "scientific-figure-builder" / "config.yaml"
    )
    controller.selectProvider("openai_vision")


def _capture_screenshots(
    controller: GuiController,
    qml_root: Any,
    output_dir: Path,
) -> None:
    app = QApplication.instance()
    assert app is not None
    for page, filename in (
        ("models", "gui-model-routes.png"),
        ("providers", "gui-providers.png"),
        ("credentials", "gui-credentials.png"),
    ):
        controller.setPage(page)
        width, height = PAGE_SIZES[page]
        qml_root.setProperty("width", width)
        qml_root.setProperty("height", height)
        app.processEvents()
        QTest.qWait(180)
        pixmap = qml_root.grabWindow()
        if pixmap.isNull():
            raise RuntimeError(f"Qt returned an empty image for {page}")
        destination = output_dir / filename
        if not pixmap.save(str(destination), "PNG"):
            raise RuntimeError(f"could not save {destination}")
        print(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_DIR / "assets",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    QQuickStyle.setStyle("Basic")
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="scientific-figure-readme-") as temp_dir:
        secret_store = MemorySecretStore()
        editor = GlobalConfigEditor(
            Path(temp_dir) / "config.yaml",
            secret_store=secret_store,
        )
        controller = GuiController(editor=editor, draft=editor.load())
        _seed_demo_configuration(controller)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("appController", controller)
        engine._scientific_figure_controller = controller  # type: ignore[attr-defined]
        qml_path = (
            PACKAGE_DIR
            / "figure_tools"
            / "resources"
            / "qml"
            / "Main.qml"
        )
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RuntimeError("could not load the configuration app QML")
        root = engine.rootObjects()[0]
        root.setProperty("width", PAGE_SIZES["models"][0])
        root.setProperty("height", PAGE_SIZES["models"][1])
        root.setProperty("visible", True)
        app.processEvents()
        QTest.qWait(250)
        _capture_screenshots(controller, root, output_dir)
        root.setProperty("visible", False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
