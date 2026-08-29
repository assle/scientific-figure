"""Protocol-compatible HTTP transports for external model providers."""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from figure_tools.providers.auth import (
    CredentialResolver,
    ResolvedCredential,
    SecretRedactor,
    provider_key_env,
)
from figure_tools.provider_configuration import (
    normalize_provider_base_url,
    normalize_providers,
)

from figure_tools.providers.contracts import (
    extract_json,
    vision_prompt,
)
from figure_tools.providers.transport import (
    ProviderError,
    ProviderTransport,
    RateLimitError,
    ROLE_TO_MODEL_CONFIG,
    model_config_for_role,
)

HTTP_OPENER = Callable[..., Any]
def _data_url(path: str | Path) -> str:
    path = Path(path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict[str, Any],
    opener: HTTP_OPENER,
    redactor: SecretRedactor | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method=method,
    )
    try:
        try:
            response_context = opener(request, timeout=timeout)
        except TypeError as exc:
            # Injectable fake openers from CI often accept only Request.
            if "timeout" not in str(exc):
                raise
            response_context = opener(request)
        with response_context as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if redactor is not None:
            detail = redactor.redact_text(detail)
        if exc.code == 429 or exc.code >= 500:
            raise RateLimitError(f"provider HTTP {exc.code}: {detail}") from exc
        raise ProviderError(f"provider HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        detail = redactor.redact_text(str(exc)) if redactor else str(exc)
        raise RateLimitError(f"transient provider error: {detail}") from exc


class OpenAICompatibleTransport(ProviderTransport):
    """OpenAI-compatible Images generation and Responses vision transport."""

    def __init__(self, name: str, config: dict[str, Any], *,
                 credential: str | ResolvedCredential | None = None,
                 credential_resolver: CredentialResolver | None = None,
                 redactor: SecretRedactor | None = None,
                 timeout: float = 30.0,
                 opener: HTTP_OPENER = urllib.request.urlopen) -> None:
        self.name = name
        self.base_url = normalize_provider_base_url(config.get("base_url"))
        self.key_env = provider_key_env(name, config)
        if credential is None:
            resolver = credential_resolver or CredentialResolver()
            credential = resolver.resolve(name, config)
        api_key = credential.value if isinstance(credential, ResolvedCredential) else credential
        self.supports_image_edit = bool(config.get("supports_image_edit", False))
        if not self.base_url:
            raise ProviderError(f"provider {name!r} requires base_url")
        if not api_key:
            raise ProviderError(f"{self.key_env} is not set for provider {name!r}")
        self.api_key = api_key
        self.redactor = redactor or SecretRedactor([api_key] if api_key else [])
        self.timeout = float(timeout)
        self._opener = opener

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return _request_json(
            f"{self.base_url}/{path.lstrip('/')}",
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body=body,
            opener=self._opener,
            redactor=self.redactor,
            timeout=self.timeout,
        )

    def post(
        self,
        role: str,
        model: str,
        payload: dict,
        image_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        if role in ("generation", "edits"):
            return self._image(role, model, payload, image_paths or [])
        if role == "phase_reasoning":
            return self._reasoning(model, payload)
        if role in ("reference_analysis", "validations", "final_validation"):
            return self._vision(role, model, payload, image_paths or [])
        raise ProviderError(f"unknown role {role!r}")

    def _reasoning(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            f"{payload['prompt']}\n\n"
            f"Phase context:\n{json.dumps(payload.get('context', {}), ensure_ascii=False)}\n\n"
            f"Allowed tools: {json.dumps(payload.get('allowed_tools', []))}\n"
            "Return ONLY one JSON object matching this output shape:\n"
            f"{json.dumps(payload.get('fallback_artifact', {}), ensure_ascii=False)}"
        )
        response = self._post("/responses", {
            "model": model,
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": prompt},
            ]}],
            "max_output_tokens": 8192,
            "text": {"format": {"type": "json_object"}},
        })
        return extract_json(_responses_text(response), redactor=self.redactor)

    def _image(
        self,
        role: str,
        model: str,
        payload: dict,
        image_paths: list[str],
    ) -> dict[str, Any]:
        params = payload.get("parameters", {})
        body: dict[str, Any] = {
            "model": model,
            "prompt": payload["prompt"],
            "response_format": "b64_json",
            "size": params.get("size") or "2048x2048",
        }
        if params.get("seed") is not None:
            body["seed"] = params["seed"]
        if role == "edits":
            if not self.supports_image_edit:
                raise ProviderError(
                    f"provider {self.name!r} does not support reference-image "
                    "editing; configure an image-edit provider or regenerate "
                    "the raster asset"
                )
            if not image_paths:
                raise ProviderError("image editing requires a parent image")
            body["image"] = _data_url(image_paths[0])
        response = self._post("/images/generations", body)
        if response.get("error"):
            raise ProviderError(
                f"provider image error: {self.redactor.redact_text(str(response['error']))}"
            )
        data = response.get("data") or []
        encoded = data[0].get("b64_json") if data else None
        if not encoded:
            raise ProviderError("provider returned no b64_json image")
        return {
            "image_bytes": base64.b64decode(encoded),
            "model": model,
            "seed": body.get("seed"),
        }

    def _vision(
        self,
        role: str,
        model: str,
        payload: dict,
        image_paths: list[str],
    ) -> dict[str, Any]:
        prompt = vision_prompt(role, payload)
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        content.extend(
            {"type": "input_image", "image_url": _data_url(path)}
            for path in image_paths
        )
        response = self._post("/responses", {
            "model": model,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 4096,
            "text": {"format": {"type": "json_object"}},
        })
        return extract_json(_responses_text(response), redactor=self.redactor)


def _responses_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "".join(chunks)


class AnthropicTransport(ProviderTransport):
    """Anthropic Messages-compatible vision transport."""

    def __init__(self, name: str, config: dict[str, Any], *,
                 credential: str | ResolvedCredential | None = None,
                 credential_resolver: CredentialResolver | None = None,
                 redactor: SecretRedactor | None = None,
                 timeout: float = 30.0,
                 opener: HTTP_OPENER = urllib.request.urlopen) -> None:
        self.name = name
        self.base_url = normalize_provider_base_url(config.get("base_url"))
        self.key_env = provider_key_env(name, config)
        if credential is None:
            resolver = credential_resolver or CredentialResolver()
            credential = resolver.resolve(name, config)
        api_key = credential.value if isinstance(credential, ResolvedCredential) else credential
        self.version = str(config.get("anthropic_version", "2023-06-01"))
        self.auth_scheme = str(config.get("auth_scheme", "x-api-key")).lower()
        self.messages_path = "/" + str(
            config.get("messages_path", "/messages")
        ).lstrip("/")
        if not self.base_url:
            raise ProviderError(f"provider {name!r} requires base_url")
        if not api_key:
            raise ProviderError(f"{self.key_env} is not set for provider {name!r}")
        if self.auth_scheme not in {"x-api-key", "bearer"}:
            raise ProviderError(
                f"provider {name!r} has unsupported auth_scheme "
                f"{self.auth_scheme!r}; expected x-api-key or bearer"
            )
        self.api_key = api_key
        self.redactor = redactor or SecretRedactor([api_key] if api_key else [])
        self.timeout = float(timeout)
        self._opener = opener

    def post(
        self,
        role: str,
        model: str,
        payload: dict,
        image_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        if role == "phase_reasoning":
            return self._reasoning(model, payload)
        if role not in ("reference_analysis", "validations", "final_validation"):
            raise ProviderError(
                "Anthropic Messages providers support vision analysis/validation, "
                "not image generation or editing"
            )
        prompt = vision_prompt(role, payload)
        content: list[dict[str, Any]] = []
        for path in image_paths or []:
            path_obj = Path(path)
            media_type = mimetypes.guess_type(path_obj.name)[0] or "image/png"
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(path_obj.read_bytes()).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": prompt})
        headers = {"anthropic-version": self.version}
        if self.auth_scheme == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["x-api-key"] = self.api_key
        response = _request_json(
            f"{self.base_url}{self.messages_path}",
            method="POST",
            headers=headers,
            body={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": content}],
            },
            opener=self._opener,
            redactor=self.redactor,
            timeout=self.timeout,
        )
        text = "".join(
            block.get("text", "")
            for block in response.get("content", [])
            if block.get("type") == "text"
        )
        return extract_json(text, redactor=self.redactor)

    def _reasoning(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            f"{payload['prompt']}\n\n"
            f"Phase context:\n{json.dumps(payload.get('context', {}), ensure_ascii=False)}\n\n"
            f"Allowed tools: {json.dumps(payload.get('allowed_tools', []))}\n"
            "Return ONLY one JSON object matching this output shape:\n"
            f"{json.dumps(payload.get('fallback_artifact', {}), ensure_ascii=False)}"
        )
        headers = {"anthropic-version": self.version}
        if self.auth_scheme == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["x-api-key"] = self.api_key
        response = _request_json(
            f"{self.base_url}{self.messages_path}",
            method="POST",
            headers=headers,
            body={
                "model": model,
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                ]}],
            },
            opener=self._opener,
            redactor=self.redactor,
            timeout=self.timeout,
        )
        text = "".join(
            block.get("text", "")
            for block in response.get("content", [])
            if block.get("type") == "text"
        )
        return extract_json(text, redactor=self.redactor)


class ProviderRouter(ProviderTransport):
    """Select a transport from each model role's provider reference."""

    def __init__(self, models: dict[str, dict[str, Any]],
                 providers: dict[str, dict[str, Any]], *,
                 credentials: dict[str, str | ResolvedCredential] | None = None,
                 provider_credentials: dict[str, str | ResolvedCredential] | None = None,
                 credential_resolver: CredentialResolver | None = None,
                 redactor: SecretRedactor | None = None,
                 timeout: float = 30.0,
                 opener: HTTP_OPENER = urllib.request.urlopen) -> None:
        self._routes: dict[str, str] = {}
        self._transports: dict[str, ProviderTransport] = {}
        self._providers = normalize_providers(providers)
        if credentials is None:
            credentials = provider_credentials
        self._explicit_credentials = credentials is not None
        self._credentials = dict(credentials or {})
        self._credential_resolver = credential_resolver
        self._redactor = redactor or SecretRedactor(
            value.value if isinstance(value, ResolvedCredential) else str(value)
            for value in self._credentials.values()
        )
        self._timeout = float(timeout)
        self._opener = opener
        for role in ROLE_TO_MODEL_CONFIG:
            resolved = model_config_for_role(models, role)
            if resolved is None:
                continue
            _internal_role, model_cfg = resolved
            provider_name = str(model_cfg.get("provider", "ark"))
            self._routes[role] = provider_name

    def _transport_for(self, provider_name: str) -> ProviderTransport:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ProviderError(f"unknown provider {provider_name!r}")
        credential = self._credentials.get(provider_name)
        if self._credential_resolver is not None:
            credential = self._credential_resolver.resolve(provider_name, provider)
            if isinstance(credential, ResolvedCredential):
                # Resolver-backed credentials can rotate while a Router is
                # alive. Keep the shared redactor in sync before checking the
                # transport cache so HTTP errors cannot expose the new value.
                self._redactor = SecretRedactor(
                    (*self._redactor.secrets, credential.value)
                )
        elif self._explicit_credentials and credential is None:
            # An explicit credential map is authoritative. Passing an empty
            # value keeps the transport from silently reaching into env.
            credential = ""
        transport = self._transports.get(provider_name)
        current_value = credential.value if isinstance(credential, ResolvedCredential) else credential
        if transport is not None and getattr(transport, "api_key", None) == current_value:
            return transport
        provider_type = provider["type"]
        if provider_type == "openai":
            transport = OpenAICompatibleTransport(
                provider_name, provider, credential=credential,
                redactor=self._redactor, opener=self._opener,
                timeout=self._timeout,
            )
        elif provider_type == "anthropic":
            transport = AnthropicTransport(
                provider_name, provider, credential=credential,
                redactor=self._redactor, opener=self._opener,
                timeout=self._timeout,
            )
        else:
            raise ProviderError(
                f"provider {provider_name!r} has unsupported type "
                f"{provider_type!r}"
            )
        self._transports[provider_name] = transport
        return transport

    def post(self, role: str, model: str, payload: dict,
             image_paths: list[str] | None = None) -> dict[str, Any]:
        if role not in self._routes:
            raise ProviderError(f"no provider route for role {role!r}")
        transport = self._transport_for(self._routes[role])
        return transport.post(role, model, payload, image_paths)
