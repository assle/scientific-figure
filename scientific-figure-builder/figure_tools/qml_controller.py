"""Qt Quick presentation controller for the native Configuration app.

QML owns layout and interaction. This controller exposes coarse application
actions while the existing config, credential, and connection-test services
remain the authoritative business layer.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Property, QThread, Signal, Slot

from figure_tools.config_editor import (
    ConfigEditorError,
    GlobalConfigDraft,
    GlobalConfigEditor,
    validate_provider_id,
)
from figure_tools.connection_test import ConnectionTestResult, ConnectionTestService
from figure_tools.provider_configuration import (
    MODEL_ROLE_CATALOG,
    PROVIDER_TYPES,
    PROVIDER_TYPE_FIELD_DEFAULTS,
    normalize_provider,
    normalize_provider_base_url,
    route_compatibility,
)
from figure_tools.providers.auth import (
    CredentialResolver,
    default_secret_store,
    provider_key_env,
    sanitize_error,
)

_ROLE_PRESENTATION = {
    "phase_reasoning": ("阶段推理", "为每个生命周期阶段运行独立结构化推理"),
    "vision_analyze": ("参考图分析", "读取参考图并提取结构与语义"),
    "image_generate": ("图像生成", "生成隔离的非量化视觉素材"),
    "image_edit": ("图像编辑", "使用参考图修订生成素材"),
    "vision_validate": ("视觉验证", "检查素材与最终组合图"),
}
ROLE_META = tuple(
    (definition.role, *_ROLE_PRESENTATION[definition.role])
    for definition in MODEL_ROLE_CATALOG
)


class _ConnectionThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: ConnectionTestService, kwargs: dict[str, Any]) -> None:
        super().__init__()
        self.service = service
        self.kwargs = kwargs
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = self.service.run(**self.kwargs, cancel_event=self.cancel_event)
            self.succeeded.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class GuiController(QObject):
    dataChanged = Signal()
    dirtyChanged = Signal()
    notificationChanged = Signal()
    connectionChanged = Signal()
    costConfirmationRequested = Signal()

    def __init__(
        self,
        editor: GlobalConfigEditor | None = None,
        draft: GlobalConfigDraft | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.editor = editor or GlobalConfigEditor(secret_store=default_secret_store())
        self.draft = draft or self.editor.load()
        self.connection_service_factory: Any = ConnectionTestService
        self.connection_transport_factory: Any = None
        self._provider_drafts: dict[str, dict[str, Any]] = {}
        self._role_state = self._initial_roles()
        self._selected_provider = next(iter(self.draft.providers), "")
        self._page = "models"
        self._dirty = False
        self._notification = ""
        self._notification_kind = "info"
        self._connection_running = False
        self._connection_thread: _ConnectionThread | None = None
        self._pending_connection: dict[str, Any] | None = None

    def _initial_roles(self) -> dict[str, dict[str, Any]]:
        state: dict[str, dict[str, Any]] = {}
        for role, label, description in ROLE_META:
            route = self.draft.models.get(role, {})
            state[role] = {
                "role": role,
                "label": label,
                "description": description,
                "provider": str(route.get("provider", "")) if isinstance(route, Mapping) else "",
                "model": str(route.get("model", "")) if isinstance(route, Mapping) else "",
                "inherit": role == "image_edit" and role not in self.draft.models,
            }
        return state

    @Property(str, constant=True)
    def configPath(self) -> str:  # noqa: N802
        return str(self.draft.path)

    @Property(str, notify=dataChanged)
    def page(self) -> str:
        return self._page

    @Property(bool, notify=dirtyChanged)
    def dirty(self) -> bool:
        return self._dirty

    @Property(str, notify=notificationChanged)
    def notification(self) -> str:
        return self._notification

    @Property(str, notify=notificationChanged)
    def notificationKind(self) -> str:  # noqa: N802
        return self._notification_kind

    @Property(bool, notify=connectionChanged)
    def connectionRunning(self) -> bool:  # noqa: N802
        return self._connection_running

    @Property("QVariantList", notify=dataChanged)  # pyright: ignore[reportArgumentType]
    def providerIds(self) -> list[str]:  # noqa: N802
        return self._provider_ids()

    def _provider_ids(self) -> list[str]:
        return [str(provider_id) for provider_id in self.draft.providers]

    @Property("QVariantList", notify=dataChanged)  # pyright: ignore[reportArgumentType]
    def providers(self) -> list[dict[str, Any]]:
        return [self._provider_view(provider_id) for provider_id in self._provider_ids()]

    @Property(str, notify=dataChanged)
    def selectedProviderId(self) -> str:  # noqa: N802
        return self._selected_provider

    @Property("QVariantMap", notify=dataChanged)  # pyright: ignore[reportArgumentType]
    def selectedProvider(self) -> dict[str, Any]:  # noqa: N802
        if not self._selected_provider:
            return {}
        return self._provider_view(self._selected_provider)

    @Property("QVariantList", notify=dataChanged)  # pyright: ignore[reportArgumentType]
    def roles(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._role_state[role]) for role, *_ in ROLE_META]

    @Property(str, notify=dataChanged)
    def warningText(self) -> str:  # noqa: N802
        warnings: list[str] = []
        models = self._models_for_connection()
        providers: dict[str, dict[str, Any]] = {}
        for provider_id in self._provider_ids():
            try:
                providers[provider_id] = normalize_provider(
                    provider_id, self._provider_view(provider_id), warn_legacy=False
                )
            except ValueError:
                continue
        for role, state in self._role_state.items():
            compatibility = route_compatibility(role, models, providers)
            if not compatibility.compatible and compatibility.reason != "optional route is not configured":
                warnings.append(f"{state['label']}：{compatibility.reason}")
        return "\n".join(warnings)

    def _provider_view(self, provider_id: str) -> dict[str, Any]:
        provider = self.draft.providers.get(provider_id, {})
        base = dict(provider) if isinstance(provider, Mapping) else {}
        base.update(self._provider_drafts.get(provider_id, {}))
        provider_type = str(base.get("type", PROVIDER_TYPES[0]))
        try:
            canonical = normalize_provider(
                provider_id,
                {**base, "type": provider_type},
                warn_legacy=False,
            )
        except ValueError:
            canonical = {**base, "type": provider_type}
        anthropic_defaults = PROVIDER_TYPE_FIELD_DEFAULTS["anthropic"]
        openai_defaults = PROVIDER_TYPE_FIELD_DEFAULTS["openai"]
        view = {
            "id": provider_id,
            "type": provider_type,
            "base_url": str(canonical.get("base_url", "")),
            "key_env": str(canonical.get("key_env", "")),
            "credential_id": str(base.get("credential_id", "")),
            "credential_status": (
                "Keyring 已配置" if base.get("credential_id")
                else "环境变量回退" if base.get("key_env")
                else "未配置"
            ),
            "auth_scheme": str(canonical.get(
                "auth_scheme", anthropic_defaults["auth_scheme"]
            )),
            "messages_path": str(canonical.get(
                "messages_path", anthropic_defaults["messages_path"]
            )),
            "anthropic_version": str(canonical.get(
                "anthropic_version", anthropic_defaults["anthropic_version"]
            )),
            "supports_image_edit": bool(canonical.get(
                "supports_image_edit", openai_defaults["supports_image_edit"]
            )),
            "api_key": str(base.get("api_key", "")),
        }
        for field, default in openai_defaults.items():
            if isinstance(default, bool):
                view[field] = bool(canonical.get(field, default))
        return view

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.dirtyChanged.emit()
        self.dataChanged.emit()

    def _notify(self, text: str, kind: str = "info") -> None:
        self._notification = text
        self._notification_kind = kind
        self.notificationChanged.emit()

    @Slot(str)
    def setPage(self, page: str) -> None:  # noqa: N802
        if page in {"models", "providers", "credentials", "about"}:
            self._page = page
            self.dataChanged.emit()

    @Slot(str)
    def selectProvider(self, provider_id: str) -> None:  # noqa: N802
        if provider_id in self.draft.providers:
            self._selected_provider = provider_id
            self.dataChanged.emit()

    @Slot(str, str)
    def updateProvider(self, field: str, value: str) -> None:  # noqa: N802
        if not self._selected_provider:
            return
        allowed = {
            "type", "base_url", "key_env", "auth_scheme", "messages_path",
            "anthropic_version", "api_key",
        }
        if field not in allowed:
            return
        if str(self._provider_view(self._selected_provider).get(field, "")) == value:
            return
        self._provider_drafts.setdefault(self._selected_provider, {})[field] = value
        self._mark_dirty()

    @Slot(str, bool)
    def updateProviderBool(self, field: str, value: bool) -> None:  # noqa: N802
        allowed = {
            name for name, default in PROVIDER_TYPE_FIELD_DEFAULTS["openai"].items()
            if isinstance(default, bool)
        }
        if self._selected_provider and field in allowed:
            if bool(self._provider_view(self._selected_provider).get(field, False)) == bool(value):
                return
            self._provider_drafts.setdefault(self._selected_provider, {})[field] = bool(value)
            self._mark_dirty()

    @Slot(str, str, str)
    def updateRole(self, role: str, field: str, value: str) -> None:  # noqa: N802
        if role in self._role_state and field in {"provider", "model"}:
            if str(self._role_state[role][field]) == value:
                return
            self._role_state[role][field] = value
            self._mark_dirty()

    @Slot(str, bool)
    def setRoleInheritance(self, role: str, inherited: bool) -> None:  # noqa: N802
        if role == "image_edit":
            if bool(self._role_state[role]["inherit"]) == bool(inherited):
                return
            self._role_state[role]["inherit"] = bool(inherited)
            self._mark_dirty()

    @Slot(str, result=bool)
    def addProvider(self, provider_id: str) -> bool:  # noqa: N802
        try:
            provider_id = validate_provider_id(provider_id)
            if provider_id in self.draft.providers:
                raise ConfigEditorError("Provider ID 已存在")
            provider_type = PROVIDER_TYPES[0]
            self.editor.set_provider(self.draft, provider_id, {
                "type": provider_type,
                "base_url": "",
                "key_env": provider_key_env(provider_id, {"type": provider_type}),
                **PROVIDER_TYPE_FIELD_DEFAULTS[provider_type],
            })
        except Exception as exc:  # noqa: BLE001
            self._notify(sanitize_error(exc), "error")
            return False
        self._selected_provider = provider_id
        self._mark_dirty()
        return True

    @Slot(str, result=bool)
    def renameSelectedProvider(self, new_id: str) -> bool:  # noqa: N802
        old_id = self._selected_provider
        if not old_id:
            return False
        try:
            new_id = validate_provider_id(new_id)
            self.editor.rename_provider(self.draft, old_id, new_id)
        except Exception as exc:  # noqa: BLE001
            self._notify(sanitize_error(exc), "error")
            return False
        if old_id in self._provider_drafts:
            self._provider_drafts[new_id] = self._provider_drafts.pop(old_id)
        for state in self._role_state.values():
            if state["provider"] == old_id:
                state["provider"] = new_id
        self._selected_provider = new_id
        self._mark_dirty()
        return True

    @Slot(result=bool)
    def deleteSelectedProvider(self) -> bool:  # noqa: N802
        provider_id = self._selected_provider
        references = [
            state["label"] for state in self._role_state.values()
            if state["provider"] == provider_id and not (
                state["role"] == "image_edit" and state["inherit"]
            )
        ]
        if references:
            self._notify("仍被以下角色引用：" + "、".join(references), "error")
            return False
        try:
            self._commit_role_drafts()
            self.editor.delete_provider(self.draft, provider_id)
        except Exception as exc:  # noqa: BLE001
            self._notify(sanitize_error(exc), "error")
            return False
        self._provider_drafts.pop(provider_id, None)
        self._selected_provider = next(iter(self.draft.providers), "")
        self._mark_dirty()
        return True

    @Slot()
    def clearCredential(self) -> None:  # noqa: N802
        if not self._selected_provider:
            return
        try:
            self.editor.clear_credential(self.draft, self._selected_provider)
        except Exception as exc:  # noqa: BLE001
            self._notify(sanitize_error(exc), "error")
            return
        self._provider_drafts.setdefault(self._selected_provider, {})["api_key"] = ""
        self._notify("凭据将在保存后移除；环境变量不受影响", "info")
        self._mark_dirty()

    @staticmethod
    def _normalized_provider(provider: Mapping[str, Any]) -> dict[str, Any]:
        base_url = normalize_provider_base_url(str(provider.get("base_url", "")).strip())
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConfigEditorError("Base URL 必须是 http:// 或 https:// 地址")
        provider_type = str(provider.get("type", PROVIDER_TYPES[0]))
        candidate: dict[str, Any] = {
            "type": provider_type,
            "base_url": base_url,
            "key_env": str(provider.get("key_env", "")).strip(),
        }
        for field in PROVIDER_TYPE_FIELD_DEFAULTS.get(provider_type, {}):
            candidate[field] = provider.get(field)
        try:
            return normalize_provider("draft", candidate, warn_legacy=False)
        except ValueError as exc:
            raise ConfigEditorError(str(exc)) from exc

    def _commit_drafts(self) -> None:
        for provider_id in self._provider_ids():
            view = self._provider_view(provider_id)
            normalized = self._normalized_provider(view)
            self.editor.set_provider(
                self.draft, provider_id, normalized
            )
            if view.get("api_key"):
                credential_id = view.get("credential_id") or None
                self.editor.set_credential(
                    self.draft, provider_id, str(view["api_key"]),
                    credential_id=str(credential_id) if credential_id else None,
                )
        self._commit_role_drafts()

    def _commit_role_drafts(self) -> None:
        for role, state in self._role_state.items():
            if role == "image_edit" and state["inherit"]:
                self.editor.remove_model(self.draft, role)
            else:
                self.editor.set_model(self.draft, role, {
                    "provider": state["provider"], "model": state["model"],
                })

    @Slot(result=bool)
    def save(self) -> bool:
        try:
            self._commit_drafts()
            self.editor.save(self.draft)
        except Exception as exc:  # noqa: BLE001
            self._notify(sanitize_error(exc), "error")
            return False
        self._provider_drafts.clear()
        self._dirty = False
        self.dirtyChanged.emit()
        self._notify("配置已安全保存", "success")
        self.dataChanged.emit()
        return True

    def _models_for_connection(self) -> dict[str, dict[str, Any]]:
        return {
            role: {"provider": state["provider"], "model": state["model"]}
            for role, state in self._role_state.items()
            if not (role == "image_edit" and state["inherit"])
        }

    @Slot(result=bool)
    def testConnection(self) -> bool:  # noqa: N802
        if self._connection_running or not self._selected_provider:
            return False
        try:
            provider = self._provider_view(self._selected_provider)
            normalized = {**provider, **self._normalized_provider(provider)}
            models = self._models_for_connection()
            selected = ConnectionTestService.select_role(models, self._selected_provider)
            if selected is None:
                raise ConfigEditorError("当前 Provider 没有可测试的模型路由")
            self._pending_connection = {
                "provider_id": self._selected_provider,
                "provider": normalized,
                "models": models,
                "temporary_credential": provider.get("api_key") or None,
            }
            if selected[0] == "generation":
                self.costConfirmationRequested.emit()
                return True
            self._start_connection()
            return True
        except Exception as exc:  # noqa: BLE001
            self._notify(sanitize_error(exc), "error")
            return False

    @Slot(bool)
    def confirmConnectionTest(self, accepted: bool) -> None:  # noqa: N802
        if accepted:
            self._start_connection()
        else:
            self._pending_connection = None

    def _start_connection(self) -> None:
        if not self._pending_connection:
            return
        service = self.connection_service_factory(
            resolver=CredentialResolver(secret_store=self.editor.secret_store),
            transport_factory=self.connection_transport_factory,
        )
        thread = _ConnectionThread(service, self._pending_connection)
        thread.succeeded.connect(self._connection_succeeded)
        thread.failed.connect(self._connection_failed)
        thread.finished.connect(self._connection_finished)
        self._connection_thread = thread
        self._connection_running = True
        self.connectionChanged.emit()
        self._notify("正在后台测试连接…", "info")
        thread.start()

    @Slot()
    def cancelConnection(self) -> None:  # noqa: N802
        if self._connection_thread and self._connection_thread.isRunning():
            self._connection_thread.cancel()
            self._notify("正在取消连接测试…", "info")

    def _connection_succeeded(self, result: ConnectionTestResult) -> None:
        self._notify(f"连接成功：{result.role} / {result.model}", "success")

    def _connection_failed(self, message: str) -> None:
        self._notify(message, "info" if "已取消" in message else "error")

    def _connection_finished(self) -> None:
        thread = self._connection_thread
        self._connection_thread = None
        self._connection_running = False
        self._pending_connection = None
        self.connectionChanged.emit()
        if thread:
            thread.deleteLater()

    @Slot()
    def discardChanges(self) -> None:  # noqa: N802
        self.draft = self.editor.load()
        self._provider_drafts.clear()
        self._role_state = self._initial_roles()
        self._selected_provider = next(iter(self.draft.providers), "")
        self._dirty = False
        self.dirtyChanged.emit()
        self.dataChanged.emit()


__all__ = ["GuiController", "ROLE_META"]
