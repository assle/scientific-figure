"""Connection-test service tests; all transport calls are fake."""

from __future__ import annotations

import io
import json
from pathlib import Path
import threading

import pytest

from figure_tools.connection_test import ConnectionTestError, ConnectionTestService
from figure_tools.providers.auth import MemorySecretStore
from figure_tools.providers.transport import ProviderError


MODELS = {
    "vision_analyze": {"provider": "demo", "model": "vision-model"},
    "image_generate": {"provider": "demo", "model": "image-model"},
}
PROVIDER = {
    "type": "openai", "base_url": "https://models.example/v1",
    "key_env": "DEMO_API_KEY",
}


class FakeTransport:
    def __init__(self, calls, *, error: Exception | None = None):
        self.calls = calls
        self.error = error

    def post(self, role, model, payload, image_paths=None):
        self.calls.append((role, model, list(image_paths or [])))
        if image_paths:
            assert Path(image_paths[0]).is_file()
        if self.error:
            raise self.error
        return {"checks": [], "blocking": False}


def _service(calls, error=None):
    return ConnectionTestService(
        resolver=None,
        transport_factory=lambda *_args, **_kwargs: FakeTransport(calls, error=error),
    )


def test_service_does_not_call_transport_until_run_and_prefers_vision():
    calls = []
    service = _service(calls)
    assert calls == []
    result = service.run("demo", PROVIDER, MODELS, temporary_credential="temporary-key")
    assert result.role == "reference_analysis"
    assert result.model == "vision-model"
    assert len(calls) == 1
    assert calls[0][2] == [] or not Path(calls[0][2][0]).exists()


def test_service_prefers_vision_over_phase_reasoning_for_shared_provider():
    calls = []
    models = {
        **MODELS,
        "phase_reasoning": {"provider": "demo", "model": "reasoning-model"},
    }

    result = _service(calls).run(
        "demo", PROVIDER, models, temporary_credential="temporary-key",
    )

    assert result.role == "reference_analysis"
    assert result.model == "vision-model"


def test_service_uses_fake_transport_and_cleans_minimum_image(tmp_path: Path):
    calls = []
    service = _service(calls)
    result = service.run(
        "demo", {**PROVIDER, "credential_id": "missing"},
        {"image_generate": {"provider": "demo", "model": "image-model"}},
        temporary_credential="temporary-key",
    )
    assert result.role == "generation"
    assert calls and not Path(calls[0][2][0]).exists()


def test_service_can_test_phase_reasoning_without_an_image():
    calls = []
    result = _service(calls).run(
        "demo", PROVIDER,
        {"phase_reasoning": {"provider": "demo", "model": "reasoner"}},
        temporary_credential="temporary-key",
    )
    assert result.role == "phase_reasoning"
    assert calls == [("phase_reasoning", "reasoner", [])]


def test_service_requires_a_credential_and_redacts_transport_error(monkeypatch):
    calls = []
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    with pytest.raises(ConnectionTestError, match="没有可用凭据"):
        _service(calls).run("demo", PROVIDER, MODELS)
    with pytest.raises(ConnectionTestError) as exc_info:
        _service(calls, ProviderError("provider echoed temporary-key")).run(
            "demo", PROVIDER, MODELS, temporary_credential="temporary-key"
        )
    assert "temporary-key" not in str(exc_info.value)


def test_service_can_resolve_keyring_credential_without_writing_it():
    calls = []
    store = MemorySecretStore({"credential-id": "keyring-key"})
    service = ConnectionTestService(
        resolver=__import__("figure_tools.providers.auth", fromlist=["CredentialResolver"]).CredentialResolver(store),
        transport_factory=lambda *_args, **_kwargs: FakeTransport(calls),
    )
    result = service.run(
        "demo", {**PROVIDER, "credential_id": "credential-id"}, MODELS
    )
    assert result.provider_id == "demo"
    assert [item[0] for item in store.operations] == ["get"]


def test_service_honors_cancellation_before_network_call():
    calls = []
    event = threading.Event()
    event.set()
    with pytest.raises(ConnectionTestError, match="已取消"):
        _service(calls).run(
            "demo", PROVIDER, MODELS,
            temporary_credential="temporary-key", cancel_event=event,
        )
    assert calls == []


def test_service_tests_dashscope_generation_through_native_transport():
    requests = []

    class Response:
        def __init__(self, body):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.body = io.BytesIO(raw)

        def read(self):
            return self.body.read()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request, timeout=None):
        requests.append(request)
        if request.full_url == "https://results.example/connection.png":
            return Response(b"image-bytes")
        return Response({
            "output": {"choices": [{"message": {"content": [{
                "image": "https://results.example/connection.png",
            }]}}]},
        })

    service = ConnectionTestService(opener=opener)
    result = service.run(
        "images",
        {
            "type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key_env": "DASHSCOPE_API_KEY",
        },
        {"image_generate": {"provider": "images", "model": "qwen-image-3.0"}},
        temporary_credential="temporary-key",
    )

    assert result.role == "generation"
    body = json.loads(requests[0].data)
    assert body["parameters"]["size"] == "1024*1024"
    assert body["input"]["messages"][0]["content"] == [
        {"text": "connection test; return one minimal asset"},
    ]
