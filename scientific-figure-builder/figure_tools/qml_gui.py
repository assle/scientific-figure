"""Qt Quick application bootstrap for the Configuration app."""

from __future__ import annotations

import sys
from importlib.resources import as_file, files

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from figure_tools.qml_controller import GuiController


def run_qml_gui(argv: list[str] | None = None) -> int:
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication(list(argv or []))
    app.setApplicationName("Scientific Figure Builder")
    app.setOrganizationName("Scientific Figure Builder")

    resources = files("figure_tools.resources")
    with as_file(resources.joinpath("icon.svg")) as icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))

    engine = QQmlApplicationEngine()
    controller = GuiController()
    engine.rootContext().setContextProperty("appController", controller)
    # Keep the controller alive for the entire engine lifetime.
    engine._scientific_figure_controller = controller  # type: ignore[attr-defined]
    with as_file(resources.joinpath("qml/Main.qml")) as qml_path:
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            return 1
        return app.exec()


__all__ = ["run_qml_gui"]


if __name__ == "__main__":
    raise SystemExit(run_qml_gui(sys.argv[1:]))
