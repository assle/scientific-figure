"""Native Qt configuration window for Global model/provider settings.

The module is intentionally outside the core import graph. ``figure_tools``
CLI help, ``init``, and the MCP server can run on headless hosts without
importing PySide6; only ``python -m figure_tools gui`` reaches this module.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from figure_tools.config_editor import (
    ConfigEditorError,
    GlobalConfigDraft,
    GlobalConfigEditor,
    ProviderInUseError,
    validate_provider_id,
)
from figure_tools.providers.auth import (
    credential_status,
    default_secret_store,
    sanitize_error,
)
from figure_tools.providers.generic_transport import normalize_provider_base_url

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
        QInputDialog,
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
            self._loading_provider_fields = False
            self._credential_clear_requested = False
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
            self.provider_selector.setEditable(False)
            self.provider_selector.addItems([str(item) for item in self.draft.providers])
            self.provider_selector.currentTextChanged.connect(self._load_provider_fields)
            layout.addWidget(QLabel("Provider ID"))
            provider_actions = QHBoxLayout()
            provider_actions.addWidget(self.provider_selector, 1)
            self.new_provider_button = QPushButton("新增")
            self.rename_provider_button = QPushButton("重命名")
            self.delete_provider_button = QPushButton("删除")
            self.new_provider_button.clicked.connect(self.add_provider)
            self.rename_provider_button.clicked.connect(self.rename_provider)
            self.delete_provider_button.clicked.connect(self.delete_provider)
            provider_actions.addWidget(self.new_provider_button)
            provider_actions.addWidget(self.rename_provider_button)
            provider_actions.addWidget(self.delete_provider_button)
            layout.addLayout(provider_actions)
            form = QFormLayout()
            self.provider_type = QComboBox()
            self.provider_type.addItems(["openai", "anthropic"])
            self.provider_base_url = QLineEdit()
            self.provider_base_url.setPlaceholderText("https://…")
            self.provider_key_env = QLineEdit()
            self.provider_key_env.setPlaceholderText("例如 OPENAI_API_KEY")
            self.provider_credential_id = QLineEdit()
            self.provider_credential_id.setReadOnly(True)
            self.provider_api_key = QLineEdit()
            self.provider_api_key.setEchoMode(QLineEdit.Password)
            self.provider_api_key.setPlaceholderText("留空表示保留现有凭据")
            self.credential_status_label = QLabel()
            self.clear_credential_button = QPushButton("移除已保存凭据")
            self.clear_credential_button.clicked.connect(self.clear_credential)
            self.provider_auth_scheme = QComboBox()
            self.provider_auth_scheme.addItems(["x-api-key", "bearer"])
            self.provider_messages_path = QLineEdit()
            self.provider_messages_path.setPlaceholderText("/messages")
            self.provider_anthropic_version = QLineEdit()
            self.provider_anthropic_version.setPlaceholderText("2023-06-01")
            self.provider_supports_edit = QCheckBox("支持参考图编辑")
            form.addRow("Provider 类型", self.provider_type)
            form.addRow("Base URL", self.provider_base_url)
            form.addRow("环境变量名", self.provider_key_env)
            form.addRow("Credential ID", self.provider_credential_id)
            form.addRow("API Key（可选）", self.provider_api_key)
            form.addRow("凭据状态", self.credential_status_label)
            form.addRow("", self.clear_credential_button)
            form.addRow("认证方式", self.provider_auth_scheme)
            form.addRow("Messages path", self.provider_messages_path)
            form.addRow("Anthropic version", self.provider_anthropic_version)
            form.addRow("OpenAI 能力", self.provider_supports_edit)
            layout.addLayout(form)
            for widget in (
                self.provider_type, self.provider_base_url, self.provider_key_env,
                self.provider_api_key, self.provider_auth_scheme,
                self.provider_messages_path, self.provider_anthropic_version,
                self.provider_supports_edit,
            ):
                if isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(self._on_field_changed)
                elif isinstance(widget, QCheckBox):
                    widget.toggled.connect(self._on_field_changed)
                else:
                    widget.textChanged.connect(self._on_field_changed)
            hint = QLabel(
                "API Key 使用密码模式且只在点击保存后写入系统钥匙串；打开已有 Provider 时不会回填完整 Key。"
            )
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
            if self._loading_provider_fields:
                return
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
            self._loading_provider_fields = True
            try:
                provider = self.draft.providers.get(provider_id, {})
                if not isinstance(provider, Mapping):
                    provider = {}
                self.provider_type.setCurrentText(_provider_type(provider) or "openai")
                self.provider_base_url.setText(str(provider.get("base_url", "")))
                self.provider_key_env.setText(str(provider.get("key_env", "")))
                self.provider_credential_id.setText(str(provider.get("credential_id", "")))
                self.provider_api_key.clear()
                self.provider_auth_scheme.setCurrentText(
                    str(provider.get("auth_scheme", "x-api-key"))
                )
                self.provider_messages_path.setText(
                    str(provider.get("messages_path", "/messages"))
                )
                self.provider_anthropic_version.setText(
                    str(provider.get("anthropic_version", "2023-06-01"))
                )
                self.provider_supports_edit.setChecked(
                    bool(provider.get("supports_image_edit", False))
                )
                status = credential_status(
                    None,
                    configured=bool(provider.get("credential_id") or provider.get("key_env")),
                )
                if provider.get("credential_id"):
                    self.credential_status_label.setText("Keyring 凭据已配置（不会显示 Key）")
                elif status["configured"]:
                    self.credential_status_label.setText("可使用环境变量回退（不显示 Key）")
                else:
                    self.credential_status_label.setText("未配置")
                self._credential_clear_requested = False
            finally:
                self._loading_provider_fields = False

        @staticmethod
        def _validate_base_url(value: str) -> str:
            normalized = normalize_provider_base_url(value.strip())
            if not normalized:
                return ""
            parsed = urlparse(normalized)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConfigEditorError("Base URL 必须是 http:// 或 https:// 地址")
            return normalized

        def _provider_values(self) -> dict[str, Any]:
            return {
                "type": self.provider_type.currentText(),
                "base_url": self._validate_base_url(self.provider_base_url.text()),
                "key_env": self.provider_key_env.text().strip(),
                "auth_scheme": self.provider_auth_scheme.currentText(),
                "messages_path": self.provider_messages_path.text().strip() or "/messages",
                "anthropic_version": self.provider_anthropic_version.text().strip() or "2023-06-01",
                "supports_image_edit": self.provider_supports_edit.isChecked(),
            }

        def _refresh_provider_choices(self) -> None:
            provider_ids = [str(item) for item in self.draft.providers]
            for widgets in self.role_widgets.values():
                combo = widgets["provider"]
                current = combo.currentText()  # type: ignore[attr-defined]
                combo.blockSignals(True)  # type: ignore[attr-defined]
                combo.clear()  # type: ignore[attr-defined]
                combo.addItems(provider_ids)  # type: ignore[attr-defined]
                combo.setCurrentText(current)  # type: ignore[attr-defined]
                combo.blockSignals(False)  # type: ignore[attr-defined]
            current_provider = self.provider_selector.currentText()
            self.provider_selector.blockSignals(True)
            self.provider_selector.clear()
            self.provider_selector.addItems(provider_ids)
            if current_provider in provider_ids:
                self.provider_selector.setCurrentText(current_provider)
            elif provider_ids:
                self.provider_selector.setCurrentIndex(0)
            self.provider_selector.blockSignals(False)

        def add_provider(self, provider_id: str | None = None) -> bool:
            if provider_id is None:
                provider_id, accepted = QInputDialog.getText(self, "新增 Provider", "Provider ID")
                if not accepted:
                    return False
            try:
                provider_id = validate_provider_id(provider_id)
                if provider_id in self.draft.providers:
                    raise ConfigEditorError("Provider ID 已存在")
                self.editor.set_provider(self.draft, provider_id, {
                    "type": "openai", "base_url": "",
                    "key_env": f"{provider_id.upper()}_API_KEY",
                    "supports_image_edit": False,
                })
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "新增失败", sanitize_error(exc))
                return False
            self._refresh_provider_choices()
            self.provider_selector.setCurrentText(provider_id)
            self._load_provider_fields(provider_id)
            self._set_dirty(True)
            return True

        def rename_provider(self, new_id: str | None = None) -> bool:
            old_id = self.provider_selector.currentText().strip()
            if not old_id:
                return False
            if new_id is None:
                new_id, accepted = QInputDialog.getText(self, "重命名 Provider", "新的 Provider ID")
                if not accepted:
                    return False
            try:
                self.editor.rename_provider(self.draft, old_id, new_id)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "重命名失败", sanitize_error(exc))
                return False
            self._refresh_provider_choices()
            self.provider_selector.setCurrentText(new_id)
            self._load_provider_fields(new_id)
            self._set_dirty(True)
            self._refresh_warnings()
            return True

        def delete_provider(self, provider_id: str | None = None, *, confirm: bool = True) -> bool:
            provider_id = (provider_id or self.provider_selector.currentText()).strip()
            if not provider_id:
                return False
            if confirm:
                choice = QMessageBox.question(
                    self, "删除 Provider", f"确定删除 Provider“{provider_id}”？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if choice != QMessageBox.Yes:
                    return False
            try:
                self.editor.delete_provider(self.draft, provider_id)
            except ProviderInUseError as exc:
                QMessageBox.warning(self, "无法删除", f"Provider 仍被引用：{exc}")
                return False
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "删除失败", sanitize_error(exc))
                return False
            self._refresh_provider_choices()
            self._load_provider_fields(self.provider_selector.currentText())
            self._set_dirty(True)
            self._refresh_warnings()
            return True

        def clear_credential(self) -> bool:
            provider_id = self.provider_selector.currentText().strip()
            if not provider_id:
                return False
            try:
                self.editor.clear_credential(self.draft, provider_id)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "凭据移除失败", sanitize_error(exc))
                return False
            self.provider_api_key.clear()
            self.provider_credential_id.clear()
            self.credential_status_label.setText("凭据将在保存后移除；环境变量不受影响")
            self._credential_clear_requested = True
            self._set_dirty(True)
            return True

        def _provider_for_warning(self, provider_id: str) -> Mapping[str, Any] | None:
            """Return the current Provider-page draft, even before Save."""

            provider = self.draft.providers.get(provider_id)
            if not isinstance(provider, Mapping):
                return None
            if provider_id != self.provider_selector.currentText().strip():
                return provider
            pending = copy.deepcopy(dict(provider))
            pending.update({
                "type": self.provider_type.currentText(),
                "base_url": self.provider_base_url.text().strip(),
                "key_env": self.provider_key_env.text().strip(),
                "supports_image_edit": self.provider_supports_edit.isChecked(),
            })
            return pending

        def _refresh_warnings(self) -> None:
            warnings: list[str] = []
            for role, widgets in self.role_widgets.items():
                if role == "image_edit" and widgets["inherit"].isChecked():  # type: ignore[attr-defined]
                    generation = self.role_widgets["image_generate"]["provider"].currentText().strip()  # type: ignore[attr-defined]
                    inherited_provider = self._provider_for_warning(generation)
                    if isinstance(inherited_provider, Mapping) and not inherited_provider.get("supports_image_edit", False):
                        warnings.append("图像编辑继承图像生成 Provider，但该 Provider 未声明参考图编辑能力；生成用途不受影响。")
                    continue
                provider_id = widgets["provider"].currentText().strip()  # type: ignore[attr-defined]
                provider = self._provider_for_warning(provider_id)
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
            provider_id = self.provider_selector.currentText().strip()
            if provider_id:
                self.editor.set_provider(self.draft, provider_id, self._provider_values())
                api_key = self.provider_api_key.text()
                if api_key:
                    existing = self.draft.providers.get(provider_id, {})
                    credential_id = (
                        str(existing.get("credential_id"))
                        if isinstance(existing, Mapping) and existing.get("credential_id")
                        else None
                    )
                    self.editor.set_credential(
                        self.draft, provider_id, api_key, credential_id=credential_id,
                    )
            for role, widgets in self.role_widgets.items():
                if role == "image_edit" and widgets["inherit"].isChecked():  # type: ignore[attr-defined]
                    self.editor.remove_model(self.draft, role)
                    continue
                self.editor.set_model(self.draft, role, {
                    "provider": widgets["provider"].currentText().strip(),  # type: ignore[attr-defined]
                    "model": widgets["model"].text().strip(),  # type: ignore[attr-defined]
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
            self.provider_api_key.clear()
            self._credential_clear_requested = False
            self._load_provider_fields(self.provider_selector.currentText())
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
