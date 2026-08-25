"""Native Qt configuration window for Global model/provider settings.

The module is intentionally outside the core import graph. ``figure_tools``
CLI help, ``init``, and the MCP server can run on headless hosts without
importing PySide6; only ``python -m figure_tools gui`` reaches this module.
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from figure_tools.config_editor import GlobalConfigDraft, GlobalConfigEditor
from figure_tools.providers.auth import default_secret_store, sanitize_error

try:  # Keep import failure local to the GUI entry point.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - exercised on headless installs
    QApplication = None  # type: ignore[assignment,misc]
    ConfigurationWindow = None  # type: ignore[assignment,misc]


ROLE_LABELS = {
    "vision_analyze": "参考图分析",
    "image_generate": "图像生成",
    "image_edit": "图像编辑",
    "vision_validate": "视觉验证",
}
ROLE_ORDER = ("vision_analyze", "image_generate", "image_edit", "vision_validate")


def _provider_type(provider: dict[str, Any]) -> str:
    provider_type = provider.get("type")
    if provider_type:
        return str(provider_type)
    protocol = provider.get("protocol")
    return {"responses": "openai", "anthropic": "anthropic"}.get(str(protocol), "")


if QApplication is not None:

    class ConfigurationWindow(QMainWindow):
        """Chinese-native editor for four model routes and their Providers."""

        def __init__(self, editor: GlobalConfigEditor | None = None,
                     draft: GlobalConfigDraft | None = None,
                     parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.editor = editor or GlobalConfigEditor(
                secret_store=default_secret_store(),
            )
            self.draft = draft or self.editor.load()
            self._saved_hash = self.draft.source_hash
            self._dirty = False
            self.role_widgets: dict[str, dict[str, QWidget]] = {}
            self.provider_widgets: dict[str, QLineEdit] = {}
            self.setWindowTitle("Scientific Figure Builder · 全局配置")
            self.resize(780, 620)
            self._build_ui()
            self._populate()
            self._refresh_warnings()
            self._set_dirty(False)

        @property
        def config_path(self) -> Path:
            return self.draft.path

        def _build_ui(self) -> None:
            root = QWidget(self)
            layout = QVBoxLayout(root)
            self.path_label = QLabel(self._path_text())
            self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(self.path_label)

            self.tabs = QTabWidget()
            self.models_page = QWidget()
            models_layout = QVBoxLayout(self.models_page)
            self._build_model_form(models_layout)
            self.tabs.addTab(self.models_page, "模型路由")
            self.providers_page = QWidget()
            providers_layout = QVBoxLayout(self.providers_page)
            self._build_provider_form(providers_layout)
            self.tabs.addTab(self.providers_page, "Provider")
            layout.addWidget(self.tabs)

            self.warning_label = QLabel()
            self.warning_label.setWordWrap(True)
            self.warning_label.setStyleSheet("color: #a15c00;")
            layout.addWidget(self.warning_label)

            footer = QHBoxLayout()
            self.dirty_label = QLabel()
            footer.addWidget(self.dirty_label)
            footer.addStretch(1)
            self.save_button = QPushButton("保存配置")
            self.save_button.clicked.connect(self.save_draft)
            footer.addWidget(self.save_button)
            layout.addLayout(footer)
            self.setCentralWidget(root)

        def _build_model_form(self, layout: QVBoxLayout) -> None:
            form = QFormLayout()
            providers = list(self.draft.providers.keys())
            for role in ROLE_ORDER:
                provider_combo = QComboBox()
                provider_combo.setEditable(True)
                provider_combo.addItems([str(item) for item in providers])
                model_edit = QLineEdit()
                model_edit.setPlaceholderText("填写 Provider 接受的模型 ID")
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(provider_combo, 1)
                row_layout.addWidget(model_edit, 2)
                widgets: dict[str, QWidget] = {
                    "provider": provider_combo, "model": model_edit,
                }
                if role == "image_edit":
                    inherit = QCheckBox("继承图像生成")
                    inherit.toggled.connect(
                        lambda checked, edit=model_edit, combo=provider_combo:
                        self._toggle_edit_inheritance(checked, edit, combo)
                    )
                    row_layout.addWidget(inherit)
                    widgets["inherit"] = inherit
                provider_combo.currentTextChanged.connect(self._on_field_changed)
                model_edit.textChanged.connect(self._on_field_changed)
                form.addRow(ROLE_LABELS[role], row)
                self.role_widgets[role] = widgets
            layout.addLayout(form)
            hint = QLabel(
                "模型 ID 为自由文本；路由只保存 Provider ID 和模型 ID，不会请求远程模型列表。"
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

        def _build_provider_form(self, layout: QVBoxLayout) -> None:
            self.provider_selector = QComboBox()
            self.provider_selector.setEditable(True)
            self.provider_selector.addItems([str(item) for item in self.draft.providers])
            self.provider_selector.currentTextChanged.connect(self._load_provider_fields)
            layout.addWidget(QLabel("Provider ID"))
            layout.addWidget(self.provider_selector)
            form = QFormLayout()
            self.provider_type = QComboBox()
            self.provider_type.addItems(["openai", "anthropic"])
            self.provider_base_url = QLineEdit()
            self.provider_base_url.setPlaceholderText("https://…")
            self.provider_key_env = QLineEdit()
            self.provider_key_env.setPlaceholderText("例如 OPENAI_API_KEY")
            self.provider_credential_id = QLineEdit()
            self.provider_credential_id.setReadOnly(True)
            form.addRow("Provider 类型", self.provider_type)
            form.addRow("Base URL", self.provider_base_url)
            form.addRow("环境变量名", self.provider_key_env)
            form.addRow("Credential ID", self.provider_credential_id)
            layout.addLayout(form)
            for widget in (
                self.provider_type, self.provider_base_url, self.provider_key_env,
            ):
                if isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(self._on_field_changed)
                else:
                    widget.textChanged.connect(self._on_field_changed)
            self.provider_selector.currentTextChanged.connect(self._load_provider_fields)
            hint = QLabel("API Key 只保存到系统钥匙串；这里不会显示或写入 Key 本身。")
            hint.setWordWrap(True)
            layout.addWidget(hint)
            layout.addStretch(1)

        def _populate(self) -> None:
            for role, widgets in self.role_widgets.items():
                route = self.draft.models.get(role, {})
                if not isinstance(route, Mapping):
                    route = {}
                widgets["provider"].setCurrentText(str(route.get("provider", "")))  # type: ignore[attr-defined]
                widgets["model"].setText(str(route.get("model", "")))  # type: ignore[attr-defined]
                if role == "image_edit":
                    inherit = widgets["inherit"]  # type: ignore[assignment]
                    inherited = role not in self.draft.models
                    inherit.setChecked(inherited)  # type: ignore[attr-defined]
                    self._toggle_edit_inheritance(inherited, widgets["model"], widgets["provider"])
            self._load_provider_fields(self.provider_selector.currentText())

        def _path_text(self) -> str:
            state = "（文件尚未创建）" if not self.draft.exists else ""
            return f"全局配置：{self.draft.path} {state}"

        def _toggle_edit_inheritance(self, checked: bool, model: QWidget,
                                     provider: QWidget) -> None:
            model.setEnabled(not checked)
            provider.setEnabled(not checked)
            self._on_field_changed()

        def _on_field_changed(self, *_args: object) -> None:
            self._set_dirty(True)
            self._refresh_warnings()

        def _set_dirty(self, dirty: bool) -> None:
            self._dirty = bool(dirty)
            self.dirty_label.setText("● 有未保存更改" if dirty else "已保存")
            self.save_button.setEnabled(dirty)
            self.setWindowTitle(
                "Scientific Figure Builder · 全局配置" + (" *" if dirty else "")
            )

        def _load_provider_fields(self, provider_id: str) -> None:
            provider = self.draft.providers.get(provider_id, {})
            if not isinstance(provider, Mapping):
                provider = {}
            self.provider_type.setCurrentText(_provider_type(provider) or "openai")
            self.provider_base_url.setText(str(provider.get("base_url", "")))
            self.provider_key_env.setText(str(provider.get("key_env", "")))
            self.provider_credential_id.setText(str(provider.get("credential_id", "")))

        def _refresh_warnings(self) -> None:
            warnings: list[str] = []
            for role, widgets in self.role_widgets.items():
                if role == "image_edit" and widgets["inherit"].isChecked():  # type: ignore[attr-defined]
                    generation = self.role_widgets["image_generate"]["provider"].currentText().strip()  # type: ignore[attr-defined]
                    inherited_provider = self.draft.providers.get(generation)
                    if isinstance(inherited_provider, Mapping) and not inherited_provider.get("supports_image_edit", False):
                        warnings.append("图像编辑继承图像生成 Provider，但该 Provider 未声明参考图编辑能力；生成用途不受影响。")
                    continue
                provider_id = widgets["provider"].currentText().strip()  # type: ignore[attr-defined]
                provider = self.draft.providers.get(provider_id)
                if not isinstance(provider, Mapping):
                    if provider_id:
                        warnings.append(f"{ROLE_LABELS[role]}：Provider“{provider_id}”尚未配置。")
                    continue
                provider_type = _provider_type(provider)
                if role in {"image_generate", "image_edit"} and provider_type != "openai":
                    warnings.append(f"{ROLE_LABELS[role]}：{provider_type or '未知'} Provider 不支持图像生成。")
                if role in {"vision_analyze", "vision_validate"} and provider_type not in {"openai", "anthropic"}:
                    warnings.append(f"{ROLE_LABELS[role]}：Provider type 不受支持。")
                if role == "image_edit" and not provider.get("supports_image_edit", False):
                    warnings.append("图像编辑 Provider 未声明参考图编辑能力；保存后仍保留生成用途。")
            self.warning_label.setText("\n".join(f"⚠ {item}" for item in warnings))

        def _collect_draft(self) -> None:
            for role, widgets in self.role_widgets.items():
                if role == "image_edit" and widgets["inherit"].isChecked():  # type: ignore[attr-defined]
                    self.editor.remove_model(self.draft, role)
                    continue
                self.editor.set_model(self.draft, role, {
                    "provider": widgets["provider"].currentText().strip(),  # type: ignore[attr-defined]
                    "model": widgets["model"].text().strip(),  # type: ignore[attr-defined]
                })
            provider_id = self.provider_selector.currentText().strip()
            if provider_id:
                self.editor.set_provider(self.draft, provider_id, {
                    "type": self.provider_type.currentText(),
                    "base_url": self.provider_base_url.text().strip(),
                    "key_env": self.provider_key_env.text().strip(),
                })

        def save_draft(self) -> bool:
            try:
                self._collect_draft()
                self.editor.save(self.draft)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "保存失败", sanitize_error(exc))
                return False
            self._saved_hash = self.draft.source_hash
            self.path_label.setText(self._path_text())
            self._set_dirty(False)
            self._refresh_warnings()
            return True

        def closeEvent(self, event) -> None:  # noqa: N802
            if not self._dirty:
                event.accept()
                return
            choice = QMessageBox.question(
                self, "未保存更改", "是否保存当前配置？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if choice == QMessageBox.Save and self.save_draft():
                event.accept()
            elif choice == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()


def run_gui(argv: list[str] | None = None) -> int:
    """Start the native configuration window and return its exit code."""

    if QApplication is None:
        print("GUI requires the PySide6 optional dependency", file=sys.stderr)
        return 1
    app = QApplication.instance() or QApplication(list(argv or []))
    window = ConfigurationWindow()
    window.show()
    return app.exec()


__all__ = ["ConfigurationWindow", "ROLE_LABELS", "run_gui"]
