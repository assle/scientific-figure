"""Provider credential resolution and secret-safe error handling.

This module is the only place that knows how a configured Provider obtains a
credential. HTTP transports receive the resolved value explicitly; they do
not inspect ``os.environ`` themselves. The interfaces are also injectable for
headless tests and the future GUI workflow.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

REDACTED = "***REDACTED***"
KEYRING_SERVICE = "scientific-figure-builder"


class SecretStore(Protocol):
    """Minimal secret-store seam used by the resolver and config editor."""

    def get(self, credential_id: str) -> str | None: ...
    def set(self, credential_id: str, value: str) -> None: ...
    def delete(self, credential_id: str) -> None: ...


class CredentialError(RuntimeError):
    """Base class for non-secret credential failures."""


class SecretStoreUnavailable(CredentialError):
    """Raised when a secure store cannot be used for a requested write."""


class SecretStoreReadError(CredentialError):
    """A secure store exists but could not be read."""


class KeyringSecretStore:
    """Adapter for the optional ``keyring`` package.

    Importing this class is safe on servers without Keyring installed. The
    package is loaded only when an instance is created, and all backend errors
    are converted to our secret-free application errors.
    """

    def __init__(self, *, service: str = KEYRING_SERVICE, backend: Any = None) -> None:
        self.service = service
        if backend is None:
            try:
                import keyring  # type: ignore[import-not-found]
            except Exception as exc:  # noqa: BLE001
                raise SecretStoreUnavailable(
                    "secure system credential backend is unavailable"
                ) from exc
            backend = keyring
        self.backend = backend

    def get(self, credential_id: str) -> str | None:
        try:
            return self.backend.get_password(self.service, credential_id)
        except Exception as exc:  # noqa: BLE001
            raise SecretStoreReadError(
                "secure system credential backend could not read the credential"
            ) from exc

    def set(self, credential_id: str, value: str) -> None:
        try:
            self.backend.set_password(self.service, credential_id, value)
        except Exception as exc:  # noqa: BLE001
            raise SecretStoreUnavailable(
                "secure system credential backend could not save the credential"
            ) from exc

    def delete(self, credential_id: str) -> None:
        try:
            self.backend.delete_password(self.service, credential_id)
        except Exception as exc:  # noqa: BLE001
            # Deleting an already absent credential is idempotent for config
            # cleanup; other backend failures remain explicit.
            if type(exc).__name__ in {"PasswordDeleteError", "NotFoundError"}:
                return
            raise SecretStoreUnavailable(
                "secure system credential backend could not delete the credential"
            ) from exc


class MemorySecretStore:
    """In-memory SecretStore for unit/integration tests; never a persistence backend."""

    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        self.values = dict(initial or {})
        self.operations: list[tuple[str, str]] = []

    def get(self, credential_id: str) -> str | None:
        self.operations.append(("get", credential_id))
        return self.values.get(credential_id)

    def set(self, credential_id: str, value: str) -> None:
        self.operations.append(("set", credential_id))
        self.values[credential_id] = value

    def delete(self, credential_id: str) -> None:
        self.operations.append(("delete", credential_id))
        self.values.pop(credential_id, None)


# Public test seam name used by integration callers; it is deliberately an
# in-memory implementation and is never selected as a production fallback.
FakeSecretStore = MemorySecretStore


def new_credential_id() -> str:
    """Return the stable UUID reference stored in global configuration."""

    return str(uuid.uuid4())


def default_secret_store() -> SecretStore | None:
    """Best-effort system-store adapter for desktop-capable callers."""

    try:
        return KeyringSecretStore()
    except SecretStoreUnavailable:
        return None


def credential_status(
    credential: ResolvedCredential | None,
    *,
    configured: bool = False,
) -> dict[str, Any]:
    """Return non-secret status suitable for CLI/GUI diagnostics."""

    return {
        "configured": bool(configured or credential is not None),
        "source": credential.source if credential is not None else None,
        "credential_id": credential.credential_id if credential is not None else None,
        "key_env": credential.key_env if credential is not None else None,
    }


@dataclass(frozen=True)
class ResolvedCredential:
    """A credential value plus non-secret provenance metadata."""

    value: str = field(repr=False)
    source: str
    provider_name: str
    key_env: str
    credential_id: str | None = None

    @property
    def credential(self) -> str:
        """Compatibility spelling for callers that use credential terminology."""

        return self.value


def provider_key_env(name: str, config: Mapping[str, Any]) -> str:
    """Return the configured env-var name, preserving legacy derivation."""

    configured = config.get("key_env")
    if configured is not None and str(configured).strip():
        return str(configured)
    provider_type = config.get("type")
    if provider_type is None and config.get("protocol") == "anthropic":
        provider_type = "anthropic"
    if provider_type == "anthropic":
        return "ANTHROPIC_API_KEY"
    return f"{name.upper()}_API_KEY"


class CredentialResolver:
    """Resolve Keyring-backed credentials before environment credentials."""

    def __init__(
        self,
        secret_store: SecretStore | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.secret_store = secret_store
        self.environ = os.environ if environ is None else environ
        self.last_warning: CredentialError | None = None

    def resolve(
        self,
        provider_name: str,
        config: Mapping[str, Any],
    ) -> ResolvedCredential | None:
        key_env = provider_key_env(provider_name, config)
        credential_id = config.get("credential_id")
        self.last_warning = None
        if credential_id and self.secret_store is not None:
            try:
                value = self.secret_store.get(str(credential_id))
            except Exception:  # noqa: BLE001 - adapters expose backend errors
                # A read failure must not prevent a headless environment
                # fallback. The warning deliberately contains no backend text.
                value = None
                self.last_warning = SecretStoreReadError(
                    f"secure credential store unavailable for {provider_name!r}"
                )
            if value:
                return ResolvedCredential(
                    value=str(value), source="keyring",
                    provider_name=provider_name, key_env=key_env,
                    credential_id=str(credential_id),
                )
        value = self.environ.get(key_env)
        if value:
            return ResolvedCredential(
                value=str(value), source="environment",
                provider_name=provider_name, key_env=key_env,
                credential_id=str(credential_id) if credential_id else None,
            )
        return None

    def resolve_all(
        self,
        providers: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, ResolvedCredential]:
        resolved: dict[str, ResolvedCredential] = {}
        for name, config in providers.items():
            credential = self.resolve(str(name), config)
            if credential is not None:
                resolved[str(name)] = credential
        return resolved

    resolve_provider = resolve
    resolve_for_provider = resolve

    def resolve_values(
        self, providers: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, str]:
        return {name: item.value for name, item in self.resolve_all(providers).items()}


def resolve_provider_credentials(
    providers: Mapping[str, Mapping[str, Any]],
    *,
    secret_store: SecretStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, ResolvedCredential]:
    """Resolve all configured providers through the single auth seam."""

    return CredentialResolver(secret_store, environ=environ).resolve_all(providers)


class SecretRedactor:
    """Replace every configured secret in text and exception messages."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        unique = {str(secret) for secret in secrets if secret}
        # Longer values first prevents a short shared prefix from exposing the
        # suffix of a longer credential.
        self.secrets = tuple(sorted(unique, key=len, reverse=True))

    def redact_text(self, text: str) -> str:
        safe = str(text)
        for secret in self.secrets:
            safe = safe.replace(secret, REDACTED)
        return safe

    def safe_exception(self, error: BaseException) -> str:
        return self.redact_text(f"{type(error).__name__}: {error}")

    def __call__(self, text: str) -> str:
        return self.redact_text(text)


def sanitize_error(error: BaseException | str, secrets: Iterable[str] = ()) -> str:
    """Return an independently testable, secret-safe error message."""

    redactor = SecretRedactor(secrets)
    if isinstance(error, BaseException):
        return redactor.safe_exception(error)
    return redactor.redact_text(str(error))


def get_api_key(
    env_var: str = "SCIENTIFIC_FIGURE_API_KEY",
    file_path: str | Path | None = None,
) -> str | None:
    """Backward-compatible helper for legacy callers."""

    if env_var in os.environ:
        return os.environ[env_var]
    if file_path is not None:
        path = Path(file_path)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return None


def redact(text: str, key: str | None) -> str:
    """Backward-compatible single-secret redaction helper."""

    return SecretRedactor([key] if key else []).redact_text(text)


def looks_like_secret(value: str) -> bool:
    """Conservative helper for config/snapshot safety checks."""

    normalized = value.strip().lower()
    if normalized in {"credential_id", "key_env"}:
        return False
    return bool(re.search(
        r"(?:sk-|api[_-]?key|access[_-]?key|private[_-]?key|secret|token|password|credential)",
        value, re.I,
    ))


__all__ = [
    "KEYRING_SERVICE", "REDACTED", "CredentialError", "CredentialResolver",
    "FakeSecretStore", "KeyringSecretStore", "MemorySecretStore",
    "ResolvedCredential", "SecretRedactor", "SecretStore", "SecretStoreReadError",
    "SecretStoreUnavailable", "credential_status", "default_secret_store",
    "get_api_key", "looks_like_secret", "new_credential_id", "provider_key_env",
    "redact", "resolve_provider_credentials", "sanitize_error",
]
