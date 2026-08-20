"""Tests for OpenAI- and Anthropic-compatible transports (no network)."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from figure_tools.ark.generic_transport import (
    AnthropicTransport,
    OpenAICompatibleTransport,
    ProviderRouter,
)
from figure_tools.ark.transport import ArkError


class _FakeResponse:
    def __init__(self, body: dict[str, Any]):
        self._body = io.BytesIO(json.dumps(body).encode("utf-8"))

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _png(path: Path) -> None:
    Image.new("RGB", (2, 2), "white").save(path, format="PNG")


def test_configured_providers_merge_user_and_project(tmp_path: Path, monkeypatch):
    from figure_tools.config import configured_models, configured_providers

    user = tmp_path / "user.yaml"
    user.write_text(
        "\n".join((
            "providers:",
            "  openai: {type: openai, base_url: https://api.example/v1}",
            "models:",
            "  image_generate: {model: image-model, provider: openai}",
            "  vision_analyze: {model: vision-model, provider: openai}",
            "  vision_validate: {model: validation-model, provider: openai}",
        )) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SCIENTIFIC_FIGURE_CONFIG", str(user))
    project = tmp_path / ".scientific-figure"
    project.mkdir()
    (project / "project.yaml").write_text(
        "providers:\n  openai: {base_url: https://project.example/v1}\n",
        encoding="utf-8",
    )

    assert configured_providers(tmp_path)["openai"]["base_url"] == (
        "https://project.example/v1"
    )
    assert configured_providers(tmp_path)["openai"]["type"] == "openai"
    assert configured_models(tmp_path, environ={})["image_generate"]["provider"] == "openai"


def test_legacy_responses_protocol_has_actionable_migration(tmp_path: Path, monkeypatch):
    from figure_tools.config import configured_providers

    user = tmp_path / "user.yaml"
    user.write_text(
        "providers:\n"
        "  legacy: {protocol: responses, base_url: https://api.example/v1}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SCIENTIFIC_FIGURE_CONFIG", str(user))

    with pytest.warns(FutureWarning, match="use type: openai"):
        providers = configured_providers(None)

    assert providers["legacy"]["type"] == "openai"
    assert "protocol" not in providers["legacy"]


def test_openai_vision_uses_responses_api(tmp_path: Path, monkeypatch):
    image = tmp_path / "input.png"
    _png(image)
    requests = []

    def opener(request):
        requests.append(request)
        assert request.full_url == "https://models.example/v1/responses"
        return _FakeResponse({
            "output": [{
                "content": [{"type": "output_text", "text": '{\"panels\": []}'}],
            }],
        })

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {"type": "openai", "base_url": "https://models.example/v1",
         "key_env": "CUSTOM_API_KEY"},
        opener=opener,
    )
    result = transport.post("reference_analysis", "vision-model", {}, [image])
    assert result == {"panels": []}
    assert requests[0].get_header("Authorization") == "Bearer test-key"


def test_openai_complete_operation_url_is_normalized_to_api_root(
    tmp_path: Path, monkeypatch,
):
    image = tmp_path / "input.png"
    _png(image)

    def opener(request):
        assert request.full_url == "https://models.example/v1/responses"
        return _FakeResponse({"output_text": '{"panels": []}'})

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1/responses/",
            "key_env": "CUSTOM_API_KEY",
        },
        opener=opener,
    )

    assert transport.post("reference_analysis", "vision-model", {}, [image]) == {
        "panels": [],
    }


def test_openai_image_uses_b64_json(tmp_path: Path, monkeypatch):
    encoded = base64.b64encode(b"image-bytes").decode("ascii")
    requests = []

    def opener(request):
        requests.append(request)
        assert request.full_url == "https://models.example/v1/images/generations"
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {"type": "openai", "base_url": "https://models.example/v1",
         "key_env": "CUSTOM_API_KEY"},
        opener=opener,
    )
    result = transport.post("generation", "image-model", {"prompt": "draw"}, [])
    assert result["image_bytes"] == b"image-bytes"
    assert json.loads(requests[0].data)["prompt"] == "draw"


def test_anthropic_vision_uses_messages_api(tmp_path: Path, monkeypatch):
    image = tmp_path / "input.png"
    _png(image)
    requests = []

    def opener(request):
        requests.append(request)
        assert request.full_url == "https://anthropic.example/v1/messages"
        return _FakeResponse({
            "content": [{"type": "text", "text": '{\"blocking\": false}'}],
        })

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    transport = AnthropicTransport(
        "anthropic",
        {"type": "anthropic", "base_url": "https://anthropic.example/v1"},
        opener=opener,
    )
    result = transport.post("validations", "vision-model", {}, [image])
    assert result == {"blocking": False}
    assert requests[0].get_header("X-api-key") == "test-key"


def test_agent_plan_anthropic_uses_bearer_and_v1_messages(
    tmp_path: Path, monkeypatch,
):
    image = tmp_path / "input.png"
    _png(image)
    requests = []

    def opener(request):
        requests.append(request)
        assert request.full_url == (
            "https://ark.cn-beijing.volces.com/api/plan/v1/messages"
        )
        return _FakeResponse({
            "content": [{"type": "text", "text": '{"blocking": false}'}],
        })

    monkeypatch.setenv("ARK_API_KEY", "agent-plan-key")
    transport = AnthropicTransport(
        "anthropic",
        {
            "type": "anthropic",
            "base_url": "https://ark.cn-beijing.volces.com/api/plan",
            "key_env": "ARK_API_KEY",
            "auth_scheme": "bearer",
            "messages_path": "/v1/messages",
        },
        opener=opener,
    )

    result = transport.post("validations", "vision-model", {}, [image])

    assert result == {"blocking": False}
    assert requests[0].get_header("Authorization") == "Bearer agent-plan-key"
    assert requests[0].get_header("X-api-key") is None


def test_anthropic_rejects_image_generation(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    transport = AnthropicTransport(
        "anthropic",
        {"type": "anthropic", "base_url": "https://anthropic.example/v1"},
    )
    try:
        transport.post("generation", "image-model", {"prompt": "draw"})
    except ArkError as exc:
        assert "not image generation" in str(exc)
    else:
        raise AssertionError("expected ArkError")


def test_provider_router_rejects_unknown_provider():
    models = {
        "vision_analyze": {"model": "vision-model", "provider": "missing"},
    }
    router = ProviderRouter(models, {})

    with pytest.raises(ArkError, match="unknown provider"):
        router.post("reference_analysis", "vision-model", {})


def test_provider_router_reuses_generation_provider_for_optional_edits(
    tmp_path: Path, monkeypatch,
):
    encoded = base64.b64encode(b"edited-image").decode("ascii")
    parent = tmp_path / "parent.png"
    _png(parent)

    def opener(request):
        assert request.full_url == "https://models.example/v1/images/generations"
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    router = ProviderRouter(
        {"image_generate": {"model": "seedream", "provider": "openai"}},
        {"openai": {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
            "supports_image_edit": True,
        }},
        opener=opener,
    )

    result = router.post(
        "edits", "seedream", {"prompt": "make it blue"}, [parent],
    )

    assert result["image_bytes"] == b"edited-image"


def test_provider_router_does_not_require_unused_provider_credentials(
    monkeypatch,
):
    encoded = base64.b64encode(b"image").decode("ascii")

    def opener(_request):
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    monkeypatch.setenv("OPENAI_TEST_KEY", "openai-key")
    monkeypatch.delenv("ANTHROPIC_TEST_KEY", raising=False)
    router = ProviderRouter(
        {
            "image_generate": {"model": "image-model", "provider": "openai"},
            "vision_analyze": {"model": "vision-model", "provider": "missing"},
        },
        {
            "openai": {
                "type": "openai",
                "base_url": "https://models.example/v1",
                "key_env": "OPENAI_TEST_KEY",
            },
        },
        opener=opener,
    )

    result = router.post("generation", "image-model", {"prompt": "draw"})

    assert result["image_bytes"] == b"image"


def test_configured_provider_instance_may_be_named_ark(monkeypatch):
    encoded = base64.b64encode(b"image").decode("ascii")
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-key")
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    router = ProviderRouter(
        {"image_generate": {"model": "image-model", "provider": "ark"}},
        {"ark": {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
        }},
        opener=lambda _request: _FakeResponse({
            "data": [{"b64_json": encoded}],
        }),
    )

    result = router.post("generation", "image-model", {"prompt": "draw"})

    assert result["image_bytes"] == b"image"


def test_openai_provider_can_reject_unsupported_reference_image_edit(
    tmp_path: Path, monkeypatch,
):
    parent = tmp_path / "parent.png"
    _png(parent)
    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
        },
        opener=lambda _request: pytest.fail("unsupported edit must not make a request"),
    )

    with pytest.raises(ArkError, match="does not support reference-image editing"):
        transport.post("edits", "image-model", {"prompt": "change it"}, [parent])
