"""Tests for OpenAI- and Anthropic-compatible transports (no network)."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from figure_tools.providers.generic_transport import (
    AnthropicTransport,
    DashScopeNativeTransport,
    OpenAICompatibleTransport,
    ProviderRouter,
)
from figure_tools.providers.transport import ProviderError


class _FakeResponse:
    def __init__(self, body: dict[str, Any] | bytes):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self._body = io.BytesIO(raw)

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


def test_openai_vision_starts_with_small_structured_output_budget(
    tmp_path: Path, monkeypatch,
):
    image = tmp_path / "multi-panel.png"
    _png(image)
    requests = []

    def opener(request):
        requests.append(request)
        return _FakeResponse({
            "status": "completed",
            "output_text": json.dumps({
                "panels": [
                    {"panel_id": f"panel-{index}", "bbox": [0, 0, 1, 1]}
                    for index in range(12)
                ],
                "objects": [],
                "text_candidates": [],
                "confidence": 0.9,
                "uncertainties": [],
            }),
        })

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
        },
        opener=opener,
    )

    result = transport.post(
        "reference_analysis", "vision-model", {}, [image],
    )

    assert len(result["panels"]) == 12
    assert json.loads(requests[0].data)["max_output_tokens"] == 4096


def test_openai_vision_surfaces_incomplete_response_reason(tmp_path: Path, monkeypatch):
    image = tmp_path / "multi-panel.png"
    _png(image)

    def opener(_request):
        return _FakeResponse({
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output_text": '{"panels":[{"panel_id":"partial-secret"',
        })

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
        },
        opener=opener,
    )

    with pytest.raises(ProviderError, match="incomplete.*max_output_tokens") as exc_info:
        transport.post("reference_analysis", "vision-model", {}, [image])

    assert "partial-secret" not in str(exc_info.value)


def test_openai_transport_accepts_explicit_credential_without_environment(
    tmp_path: Path, monkeypatch,
):
    image = tmp_path / "input.png"
    _png(image)
    monkeypatch.delenv("CUSTOM_API_KEY", raising=False)
    requests = []

    def opener(request):
        requests.append(request)
        return _FakeResponse({"output_text": '{"panels": []}'})

    transport = OpenAICompatibleTransport(
        "custom",
        {"type": "openai", "base_url": "https://models.example/v1",
         "key_env": "CUSTOM_API_KEY"},
        credential="injected-secret",
        opener=opener,
    )
    assert transport.post("reference_analysis", "vision-model", {}, [image]) == {
        "panels": [],
    }
    assert requests[0].get_header("Authorization") == "Bearer injected-secret"


def test_provider_http_error_redacts_all_explicit_credentials(monkeypatch):
    from urllib.error import HTTPError

    def opener(request):
        raise HTTPError(
            request.full_url, 400, "bad", {},
            io.BytesIO(b"token=first-secret and token=second-secret"),
        )

    router = ProviderRouter(
        {"image_generate": {"model": "image-model", "provider": "openai"}},
        {"openai": {"type": "openai", "base_url": "https://models.example/v1"}},
        credentials={"openai": "first-secret"},
        opener=opener,
    )
    # Add the second value through the public redaction seam used by callers.
    router._redactor = __import__("figure_tools.providers.auth", fromlist=["SecretRedactor"]).SecretRedactor(
        ["first-secret", "second-secret"]
    )
    with pytest.raises(ProviderError) as exc_info:
        router.post("generation", "image-model", {"prompt": "draw"})
    assert "first-secret" not in str(exc_info.value)
    assert "second-secret" not in str(exc_info.value)


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


def test_dashscope_generation_uses_native_multimodal_api_and_downloads_result(
    monkeypatch,
):
    requests = []

    def opener(request, timeout=None):
        requests.append(request)
        if request.full_url == "https://results.example/asset.png":
            return _FakeResponse(b"image-bytes")
        assert request.full_url == (
            "https://dashscope.aliyuncs.com/api/v1/"
            "services/aigc/multimodal-generation/generation"
        )
        return _FakeResponse({
            "output": {"choices": [{"message": {"content": [{
                "image": "https://results.example/asset.png",
            }]}}]},
            "usage": {"output_image_count": 1},
            "request_id": "request-1",
        })

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    transport = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key_env": "DASHSCOPE_API_KEY",
            "supports_seed": True,
        },
        opener=opener,
    )

    result = transport.post(
        "generation",
        "qwen-image-3.0",
        {"prompt": "draw", "parameters": {"size": "1024x1024", "seed": 7}},
    )

    assert result == {
        "image_bytes": b"image-bytes",
        "model": "qwen-image-3.0",
        "seed": 7,
    }
    request = requests[0]
    assert request.get_header("Authorization") == "Bearer test-key"
    assert json.loads(request.data) == {
        "model": "qwen-image-3.0",
        "input": {"messages": [{
            "role": "user",
            "content": [{"text": "draw"}],
        }]},
        "parameters": {"size": "1024*1024", "seed": 7},
    }


def test_dashscope_edit_sends_parent_image_in_native_message(tmp_path: Path, monkeypatch):
    parent = tmp_path / "parent.png"
    _png(parent)
    requests = []

    def opener(request, timeout=None):
        requests.append(request)
        if request.full_url == "https://results.example/edited.png":
            return _FakeResponse(b"edited-image")
        return _FakeResponse({
            "output": {"choices": [{"message": {"content": [{
                "image": "https://results.example/edited.png",
            }]}}]},
        })

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    transport = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "key_env": "DASHSCOPE_API_KEY",
            "supports_image_edit": True,
        },
        opener=opener,
    )

    result = transport.post(
        "edits",
        "qwen-image-3.0",
        {"prompt": "make it blue", "parameters": {"negative_prompt": "text"}},
        [parent],
    )

    assert result["image_bytes"] == b"edited-image"
    content = json.loads(requests[0].data)["input"]["messages"][0]["content"]
    assert content[0]["image"].startswith("data:image/png;base64,")
    assert content[1] == {"text": "make it blue"}


def test_dashscope_edit_requires_declared_capability_and_one_parent(
    tmp_path: Path, monkeypatch,
):
    parent = tmp_path / "parent.png"
    mask = tmp_path / "mask.png"
    _png(parent)
    _png(mask)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    requests = []

    incapable = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "key_env": "DASHSCOPE_API_KEY",
        },
        opener=lambda request: requests.append(request),
    )
    with pytest.raises(ProviderError, match="does not support reference-image editing"):
        incapable.post("edits", "qwen-image-3.0", {"prompt": "fix"}, [parent])

    capable = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "key_env": "DASHSCOPE_API_KEY",
            "supports_image_edit": True,
        },
        opener=lambda request: requests.append(request),
    )
    with pytest.raises(ProviderError, match="does not support mask editing"):
        capable.post("edits", "qwen-image-3.0", {"prompt": "fix"}, [parent, mask])

    assert requests == []


def test_dashscope_generation_rejects_undeclared_reference_support(
    tmp_path: Path, monkeypatch,
):
    reference = tmp_path / "reference.png"
    _png(reference)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    transport = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "key_env": "DASHSCOPE_API_KEY",
        },
        opener=lambda _request: pytest.fail("unsupported reference must not make a request"),
    )

    with pytest.raises(ProviderError, match="supports_reference_image"):
        transport.post(
            "generation", "qwen-image-3.0", {"prompt": "draw"}, [reference],
        )


def test_dashscope_reports_only_capabilities_implemented_by_adapter(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    transport = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "key_env": "DASHSCOPE_API_KEY",
            "supports_image_edit": True,
            "supports_reference_image": True,
            "supports_multi_reference": True,
            "supports_mask_edit": True,
            "supports_structure_control": True,
            "supports_native_alpha": True,
            "supports_seed": True,
            "supports_candidate_batch": True,
        },
    )

    assert transport.capabilities() == {
        "supports_image_edit": True,
        "supports_reference_image": True,
        "supports_multi_reference": True,
        "supports_mask_edit": False,
        "supports_structure_control": False,
        "supports_native_alpha": False,
        "supports_seed": True,
        "supports_candidate_batch": False,
    }


@pytest.mark.parametrize("parameter", [{"n": 2}, {"candidate_count": 2}])
def test_dashscope_rejects_unconsumed_batch_results(parameter, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    transport = DashScopeNativeTransport(
        "dashscope",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "key_env": "DASHSCOPE_API_KEY",
        },
        opener=lambda _request: pytest.fail("batch request must not be sent"),
    )

    with pytest.raises(ProviderError, match="batch candidates"):
        transport.post(
            "generation", "qwen-image-3.0",
            {"prompt": "draw", "parameters": parameter},
        )


def test_openai_generation_transmits_role_tagged_references(
    tmp_path: Path, monkeypatch,
):
    encoded = base64.b64encode(b"image-bytes").decode("ascii")
    reference = tmp_path / "style.png"
    _png(reference)
    requests = []

    def opener(request):
        requests.append(request)
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
            "supports_reference_image": True,
        },
        opener=opener,
    )

    transport.post(
        "generation",
        "image-model",
        {
            "prompt": "draw",
            "references": [{"role": "style", "strength": 0.75}],
        },
        [reference],
    )

    body = json.loads(requests[0].data)
    assert body["references"][0]["role"] == "style"
    assert body["references"][0]["strength"] == 0.75
    assert body["references"][0]["image"].startswith("data:image/png;base64,")


def test_openai_generation_rejects_undeclared_reference_support(
    tmp_path: Path, monkeypatch,
):
    reference = tmp_path / "style.png"
    _png(reference)
    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    transport = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
        },
    )

    with pytest.raises(ProviderError, match="supports_reference_image"):
        transport.post(
            "generation",
            "image-model",
            {
                "prompt": "draw",
                "references": [{"role": "style", "strength": 1.0}],
            },
            [reference],
        )


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
    except ProviderError as exc:
        assert "not image generation" in str(exc)
    else:
        raise AssertionError("expected ProviderError")


def test_provider_router_rejects_unknown_provider():
    models = {
        "vision_analyze": {"model": "vision-model", "provider": "missing"},
    }
    router = ProviderRouter(models, {})

    with pytest.raises(ProviderError, match="unknown provider"):
        router.post("reference_analysis", "vision-model", {})


def test_provider_router_requires_an_explicit_provider_id():
    with pytest.raises(ProviderError, match="Provider ID"):
        ProviderRouter(
            {"vision_analyze": {"model": "vision-model"}},
            {"ark": {"type": "openai", "base_url": "https://example.test"}},
        )


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


def test_provider_router_dispatches_image_generation_to_dashscope(monkeypatch):
    def opener(request, timeout=None):
        if request.full_url == "https://results.example/generated.png":
            return _FakeResponse(b"dashscope-image")
        return _FakeResponse({
            "output": {"choices": [{"message": {"content": [{
                "image": "https://results.example/generated.png",
            }]}}]},
        })

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    router = ProviderRouter(
        {"image_generate": {"model": "qwen-image-3.0", "provider": "images"}},
        {"images": {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key_env": "DASHSCOPE_API_KEY",
        }},
        opener=opener,
    )

    result = router.post(
        "generation", "qwen-image-3.0", {"prompt": "draw"},
    )

    assert result["image_bytes"] == b"dashscope-image"


def test_openai_edit_transmits_mask_only_when_capability_is_declared(
    tmp_path: Path, monkeypatch,
):
    encoded = base64.b64encode(b"edited-image").decode("ascii")
    parent = tmp_path / "parent.png"
    mask = tmp_path / "mask.png"
    _png(parent)
    _png(mask)
    requests = []

    def opener(request):
        requests.append(request)
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    monkeypatch.setenv("CUSTOM_API_KEY", "test-key")
    capable = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
            "supports_image_edit": True,
            "supports_mask_edit": True,
        },
        opener=opener,
    )

    capable.post("edits", "image-model", {"prompt": "fix"}, [parent, mask])

    body = json.loads(requests[0].data)
    assert body["image"].startswith("data:image/png;base64,")
    assert body["mask"].startswith("data:image/png;base64,")

    incapable = OpenAICompatibleTransport(
        "custom",
        {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "key_env": "CUSTOM_API_KEY",
            "supports_image_edit": True,
        },
        opener=opener,
    )
    with pytest.raises(ProviderError, match="supports_mask_edit"):
        incapable.post("edits", "image-model", {"prompt": "fix"}, [parent, mask])


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


def test_provider_router_can_call_with_only_keyring_credential(monkeypatch):
    from figure_tools.providers.auth import CredentialResolver, MemorySecretStore

    encoded = base64.b64encode(b"image").decode("ascii")
    credential_id = "3d6f5f6e-3d1a-4f0b-a1e8-2d2c3f4a5b6c"
    store = MemorySecretStore({credential_id: "keyring-secret"})
    monkeypatch.delenv("KEYRING_ONLY", raising=False)
    requests = []

    def opener(request):
        requests.append(request)
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    resolver = CredentialResolver(store)
    router = ProviderRouter(
        {"image_generate": {"model": "image-model", "provider": "openai"}},
        {"openai": {
            "type": "openai", "base_url": "https://models.example/v1",
            "key_env": "KEYRING_ONLY", "credential_id": credential_id,
        }},
        credential_resolver=resolver,
        opener=opener,
    )
    assert router.post("generation", "image-model", {"prompt": "draw"})[
        "image_bytes"
    ] == b"image"
    assert requests[0].get_header("Authorization") == "Bearer keyring-secret"


def test_provider_router_refreshes_keyring_value_on_next_call(monkeypatch):
    from figure_tools.providers.auth import CredentialResolver, MemorySecretStore

    encoded = base64.b64encode(b"image").decode("ascii")
    store = MemorySecretStore({"credential-id": "first-secret"})
    monkeypatch.delenv("ROTATING_KEY", raising=False)
    headers = []

    def opener(request):
        headers.append(request.get_header("Authorization"))
        return _FakeResponse({"data": [{"b64_json": encoded}]})

    router = ProviderRouter(
        {"image_generate": {"model": "image-model", "provider": "openai"}},
        {"openai": {
            "type": "openai", "base_url": "https://models.example/v1",
            "key_env": "ROTATING_KEY", "credential_id": "credential-id",
        }},
        credential_resolver=CredentialResolver(store), opener=opener,
    )
    router.post("generation", "image-model", {"prompt": "one"})
    store.set("credential-id", "second-secret")
    router.post("generation", "image-model", {"prompt": "two"})
    assert headers == ["Bearer first-secret", "Bearer second-secret"]


def test_keyring_only_http_error_redacts_resolved_credential(monkeypatch):
    from figure_tools.providers.auth import CredentialResolver, MemorySecretStore
    from urllib.error import HTTPError

    store = MemorySecretStore({"credential-id": "keyring-secret"})

    def opener(request):
        raise HTTPError(
            request.full_url, 400, "bad", {},
            io.BytesIO(b"provider echoed keyring-secret"),
        )

    router = ProviderRouter(
        {"image_generate": {"model": "image-model", "provider": "openai"}},
        {"openai": {
            "type": "openai", "base_url": "https://models.example/v1",
            "credential_id": "credential-id",
        }},
        credential_resolver=CredentialResolver(store), opener=opener,
    )
    with pytest.raises(ProviderError) as exc_info:
        router.post("generation", "image-model", {"prompt": "draw"})
    assert "keyring-secret" not in str(exc_info.value)


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

    with pytest.raises(ProviderError, match="does not support reference-image editing"):
        transport.post("edits", "image-model", {"prompt": "change it"}, [parent])
