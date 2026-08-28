"""User-triggered, minimal Provider connection testing.

The service accepts a complete draft in memory and never calls the global
configuration editor. A caller must invoke ``run`` explicitly; constructing
the service, loading a GUI draft, or saving configuration performs no network
I/O.
"""

from __future__ import annotations

import base64
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from figure_tools.providers.auth import (
    CredentialResolver,
    ResolvedCredential,
    SecretRedactor,
    sanitize_error,
)
from figure_tools.providers.generic_transport import (
    AnthropicTransport,
    OpenAICompatibleTransport,
)
from figure_tools.providers.transport import ProviderTransport

_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ConnectionTestError(RuntimeError):
    """A secret-safe, user-facing connection test failure."""


@dataclass(frozen=True)
class ConnectionTestResult:
    provider_id: str
    role: str
    model: str
    response_keys: tuple[str, ...]


class ConnectionTestService:
    """Run one deterministic minimum-capability request for a draft Provider."""

    def __init__(
        self,
        *,
        resolver: CredentialResolver | None = None,
        transport_factory: Callable[..., ProviderTransport] | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.resolver = resolver or CredentialResolver()
        self.transport_factory = transport_factory
        self.timeout = float(timeout)

    @staticmethod
    def select_role(
        models: Mapping[str, Mapping[str, Any]], provider_id: str,
    ) -> tuple[str, str] | None:
        for route_key, internal_role in (
            ("phase_reasoning", "phase_reasoning"),
            ("vision_analyze", "reference_analysis"),
            ("vision_validate", "validations"),
            ("image_generate", "generation"),
        ):
            route = models.get(route_key)
            if isinstance(route, Mapping) and str(route.get("provider", "")) == provider_id:
                model = str(route.get("model", "")).strip()
                if model:
                    return internal_role, model
        return None

    def _transport(
        self,
        provider_id: str,
        provider: Mapping[str, Any],
        credential: str | ResolvedCredential,
        redactor: SecretRedactor,
    ) -> ProviderTransport:
        if self.transport_factory is not None:
            return self.transport_factory(
                provider_id, provider, credential=credential,
            )
        provider_type = str(provider.get("type", ""))
        kwargs = {
            "credential": credential,
            "redactor": redactor,
            "timeout": self.timeout,
        }
        if provider_type == "openai":
            return OpenAICompatibleTransport(provider_id, dict(provider), **kwargs)
        if provider_type == "anthropic":
            return AnthropicTransport(provider_id, dict(provider), **kwargs)
        raise ConnectionTestError("Provider type 必须是 openai 或 anthropic")

    def run(
        self,
        provider_id: str,
        provider: Mapping[str, Any],
        models: Mapping[str, Mapping[str, Any]],
        *,
        temporary_credential: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ConnectionTestResult:
        if cancel_event is not None and cancel_event.is_set():
            raise ConnectionTestError("连接测试已取消")
        selected = self.select_role(models, provider_id)
        if selected is None:
            raise ConnectionTestError("当前 Provider 没有已绑定且有模型 ID 的路由")
        role, model = selected
        resolved = (
            ResolvedCredential(
                value=temporary_credential,
                source="temporary",
                provider_name=provider_id,
                key_env=str(provider.get("key_env", "")),
                credential_id=str(provider.get("credential_id"))
                if provider.get("credential_id") else None,
            )
            if temporary_credential
            else self.resolver.resolve(provider_id, provider)
        )
        if resolved is None:
            raise ConnectionTestError("当前 Provider 没有可用凭据")
        redactor = SecretRedactor([resolved.value])
        transport = self._transport(provider_id, provider, resolved, redactor)
        try:
            with tempfile.TemporaryDirectory(prefix="scientific-figure-connection-") as temp_dir:
                image_path = Path(temp_dir) / "minimum.png"
                image_path.write_bytes(_MINIMAL_PNG)
                if role == "generation":
                    response = transport.post(
                        role, model,
                        {"prompt": "connection test; return one minimal asset", "parameters": {"size": "1x1"}},
                        [str(image_path)],
                    )
                elif role == "phase_reasoning":
                    response = transport.post(
                        role, model,
                        {
                            "prompt": "connection test; return one compact JSON object",
                            "context": {}, "allowed_tools": [],
                            "fallback_artifact": {"status": "ok"},
                        },
                    )
                else:
                    response = transport.post(
                        role, model,
                        {"prompt": "connection test; return a compact JSON response"},
                        [str(image_path)],
                    )
                if cancel_event is not None and cancel_event.is_set():
                    raise ConnectionTestError("连接测试已取消")
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ConnectionTestError):
                raise
            raise ConnectionTestError(sanitize_error(exc, redactor.secrets)) from None
        if not isinstance(response, Mapping):
            raise ConnectionTestError("Provider 返回了无法识别的响应")
        return ConnectionTestResult(
            provider_id=provider_id,
            role=role,
            model=model,
            response_keys=tuple(sorted(str(key) for key in response.keys())),
        )


__all__ = ["ConnectionTestError", "ConnectionTestResult", "ConnectionTestService"]
