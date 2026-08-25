"""Round-trip editor for the user-scoped models/providers configuration.

The editor owns only the ``models`` and ``providers`` subtrees.  It keeps the
round-trip YAML document in memory so comments, ordering, unknown fields, and
unrelated top-level configuration survive a save.  Credential values are
queued as transient operations and never enter that document.
"""

from __future__ import annotations

import copy
import hashlib
import os
import shutil
import tempfile
import warnings
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

from figure_tools.config import user_config_path
from figure_tools.providers.auth import (
    CredentialError,
    SecretStore,
    SecretStoreUnavailable,
    looks_like_secret,
    new_credential_id,
)

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    YAML = None  # type: ignore[assignment]
    CommentedMap = dict  # type: ignore[misc,assignment]


class ConfigEditorError(RuntimeError):
    """Base class for safe global configuration editing failures."""


class ConfigConflictError(ConfigEditorError):
    """The file changed after a draft was loaded."""


class ProviderInUseError(ConfigEditorError):
    """A provider cannot be deleted while model routes reference it."""


class ConfigSerializationError(ConfigEditorError):
    """The round-trip document could not be serialized safely."""


@dataclass
class GlobalConfigDraft:
    path: Path
    data: Any
    source_hash: str | None
    exists: bool
    credential_updates: dict[str, tuple[str, str]] = field(default_factory=dict)
    credential_deletes: set[str] = field(default_factory=set)

    @property
    def models(self) -> Any:
        models = self.data.get("models")
        if not isinstance(models, Mapping):
            models = CommentedMap()
            self.data["models"] = models
        return models

    @property
    def providers(self) -> Any:
        providers = self.data.get("providers")
        if not isinstance(providers, Mapping):
            providers = CommentedMap()
            self.data["providers"] = providers
        return providers

    def public_snapshot(self) -> dict[str, Any]:
        """Return a copy suitable for diagnostics without secret values."""

        def scrub(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {
                    str(key): scrub(item)
                    for key, item in value.items()
                    if not looks_like_secret(str(key))
                }
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return copy.deepcopy(value)

        return scrub(self.data)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _merge(existing: Any, updates: Mapping[str, Any]) -> Any:
    result = copy.deepcopy(existing) if isinstance(existing, Mapping) else CommentedMap()
    for key, value in updates.items():
        if (
            key in result
            and isinstance(result[key], Mapping)
            and isinstance(value, Mapping)
        ):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class GlobalConfigEditor:
    """Load, mutate, and atomically save the user global configuration."""

    def __init__(self, path: str | Path | None = None,
                 *, secret_store: SecretStore | None = None) -> None:
        self.path = Path(path) if path is not None else user_config_path()
        self.secret_store = secret_store

    def load(self) -> GlobalConfigDraft:
        if self.path.is_file():
            if YAML is None:
                raise ConfigSerializationError(
                    "ruamel.yaml is required for comment-preserving configuration edits"
                )
            yaml = YAML(typ="rt")
            try:
                with self.path.open("r", encoding="utf-8") as stream:
                    data = yaml.load(stream)
            except Exception as exc:  # noqa: BLE001
                raise ConfigSerializationError("could not read global configuration") from exc
            if data is None:
                data = CommentedMap()
            if not isinstance(data, Mapping):
                raise ConfigSerializationError("global configuration must be a YAML mapping")
            draft = GlobalConfigDraft(
                self.path, data, _sha256(self.path), True,
            )
            self._migrate_legacy_protocols(draft)
            return draft
        return GlobalConfigDraft(self.path, CommentedMap(), None, False)

    @staticmethod
    def _migrate_legacy_protocols(draft: GlobalConfigDraft) -> None:
        protocols = {"responses": "openai", "anthropic": "anthropic"}
        for provider_id, provider in draft.providers.items():
            if not isinstance(provider, Mapping) or "protocol" not in provider:
                continue
            protocol = provider.get("protocol")
            migrated = protocols.get(protocol)
            if migrated is None:
                raise ConfigSerializationError(
                    f"provider {provider_id!r} has unsupported legacy protocol"
                )
            configured_type = provider.get("type")
            if configured_type is not None and configured_type != migrated:
                raise ConfigSerializationError(
                    f"provider {provider_id!r} has conflicting provider type"
                )
            warnings.warn(
                f"provider {provider_id!r}: protocol is deprecated; use type: {migrated}",
                FutureWarning, stacklevel=3,
            )
            provider.pop("protocol", None)
            provider["type"] = migrated

    def set_model(self, draft: GlobalConfigDraft, role: str,
                  values: Mapping[str, Any]) -> None:
        self._assert_non_secret(values)
        draft.models[role] = _merge(draft.models.get(role), values)

    def remove_model(self, draft: GlobalConfigDraft, role: str) -> None:
        draft.models.pop(role, None)

    def set_provider(self, draft: GlobalConfigDraft, provider_id: str,
                     values: Mapping[str, Any]) -> None:
        self._assert_non_secret(values)
        draft.providers[provider_id] = _merge(draft.providers.get(provider_id), values)

    @staticmethod
    def _assert_non_secret(values: Mapping[str, Any]) -> None:
        def walk(value: Any) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if looks_like_secret(str(key)):
                        raise ConfigEditorError(
                            "provider credentials must be stored in the secure system store"
                        )
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(values)

    def rename_provider(self, draft: GlobalConfigDraft, old_id: str, new_id: str) -> None:
        if old_id not in draft.providers:
            raise ConfigEditorError(f"unknown provider {old_id!r}")
        if new_id in draft.providers:
            raise ConfigEditorError(f"provider {new_id!r} already exists")
        draft.providers[new_id] = draft.providers.pop(old_id)
        for model in draft.models.values():
            if isinstance(model, Mapping) and model.get("provider") == old_id:
                model["provider"] = new_id

    def delete_provider(self, draft: GlobalConfigDraft, provider_id: str) -> None:
        references = [
            role for role, model in draft.models.items()
            if isinstance(model, Mapping) and model.get("provider") == provider_id
        ]
        if references:
            raise ProviderInUseError(
                f"provider {provider_id!r} is referenced by model roles: {', '.join(references)}"
            )
        provider = draft.providers.pop(provider_id, None)
        if isinstance(provider, Mapping) and provider.get("credential_id"):
            draft.credential_deletes.add(str(provider["credential_id"]))

    def set_credential(self, draft: GlobalConfigDraft, provider_id: str,
                       value: str, *, credential_id: str | None = None) -> str:
        if not str(value):
            raise ConfigEditorError("credential value must not be empty")
        provider = draft.providers.get(provider_id)
        if not isinstance(provider, Mapping):
            raise ConfigEditorError(f"unknown provider {provider_id!r}")
        old_id = provider.get("credential_id")
        new_id = str(credential_id or new_credential_id())
        provider["credential_id"] = new_id
        draft.credential_updates[provider_id] = (new_id, str(value))
        if old_id and str(old_id) != new_id:
            draft.credential_deletes.add(str(old_id))
        return new_id

    def _render(self, draft: GlobalConfigDraft) -> bytes:
        self._assert_non_secret(draft.data)
        if YAML is None:
            raise ConfigSerializationError(
                "ruamel.yaml is required for comment-preserving configuration edits"
            )
        yaml = YAML(typ="rt")
        yaml.default_flow_style = False
        stream = StringIO()
        try:
            yaml.dump(draft.data, stream)
        except Exception as exc:  # noqa: BLE001
            raise ConfigSerializationError("could not serialize global configuration") from exc
        return stream.getvalue().encode("utf-8")

    def _check_conflict(self, draft: GlobalConfigDraft) -> None:
        exists = self.path.is_file()
        if exists != draft.exists:
            raise ConfigConflictError(
                "global configuration changed externally; reload before saving"
            )
        if exists and draft.source_hash != _sha256(self.path):
            raise ConfigConflictError(
                "global configuration changed externally; reload before saving"
            )

    def _prepare_credentials(self, draft: GlobalConfigDraft) -> dict[str, str | None]:
        if not draft.credential_updates:
            return {}
        if self.secret_store is None:
            raise SecretStoreUnavailable(
                "secure system credential backend is required to save a credential"
            )
        previous: dict[str, str | None] = {}
        for provider_id, (credential_id, value) in draft.credential_updates.items():
            try:
                previous[credential_id] = self.secret_store.get(credential_id)
                self.secret_store.set(credential_id, value)
            except CredentialError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise SecretStoreUnavailable(
                    "secure system credential backend could not prepare the credential"
                ) from exc
        return previous

    def _rollback_credentials(self, previous: Mapping[str, str | None]) -> None:
        if self.secret_store is None:
            return
        for credential_id, old_value in previous.items():
            try:
                if old_value is None:
                    self.secret_store.delete(credential_id)
                else:
                    self.secret_store.set(credential_id, old_value)
            except Exception:  # noqa: BLE001 - preserve original save failure
                pass

    def save(self, draft: GlobalConfigDraft) -> GlobalConfigDraft:
        self._check_conflict(draft)
        rendered = self._render(draft)
        previous = self._prepare_credentials(draft)
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        backup = self.path.with_name(self.path.name + ".bak")
        mode = 0o600
        try:
            if self.path.exists():
                shutil.copy2(self.path, backup)
                mode = self.path.stat().st_mode & 0o777
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=parent,
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(rendered)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary_name, mode)
                os.replace(temporary_name, self.path)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        except Exception:
            self._rollback_credentials(previous)
            raise ConfigEditorError("could not atomically save global configuration") from None

        # Deleting old credentials is intentionally last. A cleanup failure
        # does not invalidate the committed YAML; report a safe warning.
        if self.secret_store is not None:
            for credential_id in sorted(draft.credential_deletes):
                try:
                    self.secret_store.delete(credential_id)
                except Exception:  # noqa: BLE001
                    warnings.warn(
                        "a retired system credential could not be removed",
                        RuntimeWarning, stacklevel=2,
                    )
        draft.source_hash = _sha256(self.path)
        draft.exists = True
        draft.credential_updates.clear()
        draft.credential_deletes.clear()
        return draft


def load_global_config(path: str | Path | None = None,
                       *, secret_store: SecretStore | None = None) -> GlobalConfigDraft:
    """Convenience function for callers that need one read-only draft."""

    return GlobalConfigEditor(path, secret_store=secret_store).load()


__all__ = [
    "ConfigConflictError", "ConfigEditorError", "ConfigSerializationError",
    "ConfigDraft", "ConfigurationEditor", "GlobalConfigDraft", "GlobalConfigEditor",
    "ProviderInUseError",
    "load_global_config",
]

# Small aliases keep the editor discoverable for integrations that use the
# shorter configuration vocabulary.
ConfigDraft = GlobalConfigDraft
ConfigurationEditor = GlobalConfigEditor
