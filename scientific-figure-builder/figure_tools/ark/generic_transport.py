"""Protocol-compatible HTTP transports for external model providers."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from figure_tools.ark.contracts import (
    extract_json,
    vision_prompt,
)
from figure_tools.ark.transport import (
    ArkError,
    ArkTransport,
    RateLimitError,
    ROLE_TO_MODEL_CONFIG,
    model_config_for_role,
)

HTTP_OPENER = Callable[..., Any]
_OPERATION_PATHS = ("/images/generations", "/responses", "/messages")


def _api_root(value: Any) -> str:
    root = str(value or "").rstrip("/")
    for operation_path in _OPERATION_PATHS:
        if root.endswith(operation_path):
            return root[:-len(operation_path)]
    return root


def provider_key_env(name: str, config: dict[str, Any]) -> str:
    configured = config.get("key_env")
    if configured is not None:
        return str(configured)
    provider_type = config.get("type")
    if provider_type is None and config.get("protocol") == "anthropic":
        provider_type = "anthropic"
    if provider_type == "anthropic":
        return "ANTHROPIC_API_KEY"
    return f"{name.upper()}_API_KEY"


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
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method=method,
    )
    try:
        with opener(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 429 or exc.code >= 500:
            raise RateLimitError(f"provider HTTP {exc.code}: {detail}") from exc
        raise ArkError(f"provider HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RateLimitError(f"transient provider error: {exc}") from exc


class OpenAICompatibleTransport(ArkTransport):
    """OpenAI-compatible Images generation and Responses vision transport."""

    def __init__(self, name: str, config: dict[str, Any], *,
                 opener: HTTP_OPENER = urllib.request.urlopen) -> None:
        self.name = name
        self.base_url = _api_root(config.get("base_url"))
        self.key_env = provider_key_env(name, config)
        api_key = os.environ.get(self.key_env)
        self.supports_image_edit = bool(config.get("supports_image_edit", False))
        if not self.base_url:
            raise ArkError(f"provider {name!r} requires base_url")
        if not api_key:
            raise ArkError(f"{self.key_env} is not set for provider {name!r}")
        self.api_key = api_key
        self._opener = opener

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return _request_json(
            f"{self.base_url}/{path.lstrip('/')}",
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body=body,
            opener=self._opener,
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
        if role in ("reference_analysis", "validations", "final_validation"):
            return self._vision(role, model, payload, image_paths or [])
        raise ArkError(f"unknown role {role!r}")

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
                raise ArkError(
                    f"provider {self.name!r} does not support reference-image "
                    "editing; configure an image-edit provider or regenerate "
                    "the raster asset"
                )
            if not image_paths:
                raise ArkError("image editing requires a parent image")
            body["image"] = _data_url(image_paths[0])
        response = self._post("/images/generations", body)
        if response.get("error"):
            raise ArkError(f"provider image error: {response['error']}")
        data = response.get("data") or []
        encoded = data[0].get("b64_json") if data else None
        if not encoded:
            raise ArkError("provider returned no b64_json image")
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
        return extract_json(_responses_text(response))


def _responses_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "".join(chunks)


# Backward-compatible import for callers that used the pre-v1 internal name.
ResponsesTransport = OpenAICompatibleTransport


class AnthropicTransport(ArkTransport):
    """Anthropic Messages-compatible vision transport."""

    def __init__(self, name: str, config: dict[str, Any], *,
                 opener: HTTP_OPENER = urllib.request.urlopen) -> None:
        self.name = name
        self.base_url = _api_root(config.get("base_url"))
        self.key_env = provider_key_env(name, config)
        api_key = os.environ.get(self.key_env)
        self.version = config.get("anthropic_version", "2023-06-01")
        if not self.base_url:
            raise ArkError(f"provider {name!r} requires base_url")
        if not api_key:
            raise ArkError(f"{self.key_env} is not set for provider {name!r}")
        self.api_key = api_key
        self._opener = opener

    def post(
        self,
        role: str,
        model: str,
        payload: dict,
        image_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        if role not in ("reference_analysis", "validations", "final_validation"):
            raise ArkError(
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
        response = _request_json(
            f"{self.base_url}/messages",
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.version,
            },
            body={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": content}],
            },
            opener=self._opener,
        )
        text = "".join(
            block.get("text", "")
            for block in response.get("content", [])
            if block.get("type") == "text"
        )
        return extract_json(text)


class ProviderRouter(ArkTransport):
    """Select a transport from each model role's provider reference."""

    def __init__(self, models: dict[str, dict[str, Any]],
                 providers: dict[str, dict[str, Any]], *,
                 opener: HTTP_OPENER = urllib.request.urlopen) -> None:
        self._routes: dict[str, str] = {}
        self._transports: dict[str, ArkTransport] = {}
        self._providers = providers
        self._opener = opener
        for role in ROLE_TO_MODEL_CONFIG:
            resolved = model_config_for_role(models, role)
            if resolved is None:
                continue
            internal_role, model_cfg = resolved
            provider_name = str(model_cfg.get("provider", "ark"))
            provider = providers.get(provider_name)
            if provider is not None:
                if self._provider_type(provider) not in {"openai", "anthropic"}:
                    raise ArkError(
                        f"provider {provider_name!r} has unsupported type "
                        f"{self._provider_type(provider)!r}"
                    )
            elif provider_name != "ark":
                raise ArkError(
                    f"model role {internal_role!r} references unknown provider "
                    f"{provider_name!r}"
                )
            self._routes[role] = provider_name

    @staticmethod
    def _provider_type(provider: dict[str, Any]) -> str | None:
        provider_type = provider.get("type")
        if provider_type is not None:
            return str(provider_type)
        legacy_protocol = provider.get("protocol")
        if not isinstance(legacy_protocol, str):
            return None
        return {
            "responses": "openai",
            "anthropic": "anthropic",
        }.get(legacy_protocol)

    def _transport_for(self, provider_name: str) -> ArkTransport:
        transport = self._transports.get(provider_name)
        if transport is not None:
            return transport
        if provider_name == "ark" and provider_name not in self._providers:
            from figure_tools.ark.real_transport import RealArkTransport

            transport = RealArkTransport()
        else:
            provider = self._providers[provider_name]
            provider_type = self._provider_type(provider)
            if provider_type == "openai":
                transport = OpenAICompatibleTransport(
                    provider_name, provider, opener=self._opener,
                )
            else:
                transport = AnthropicTransport(
                    provider_name, provider, opener=self._opener,
                )
        self._transports[provider_name] = transport
        return transport

    def post(self, role: str, model: str, payload: dict,
             image_paths: list[str] | None = None) -> dict[str, Any]:
        if role not in self._routes:
            raise ArkError(f"no provider route for role {role!r}")
        transport = self._transport_for(self._routes[role])
        return transport.post(role, model, payload, image_paths)
