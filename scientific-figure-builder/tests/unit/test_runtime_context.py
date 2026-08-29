from __future__ import annotations

from pathlib import Path

import pytest

from figure_tools.providers.auth import MemorySecretStore
from figure_tools.providers.transport import MockProviderTransport
from figure_tools.runtime_context import RuntimeContextError, RuntimeContextFactory
from figure_tools.state import RunState


def _config():
    return {
        "models": {
            "phase_reasoning": {"provider": "live", "model": "reason"},
            "image_generate": {"provider": "live", "model": "image"},
            "vision_validate": {"provider": "missing", "model": "vision"},
        },
        "providers": {
            "live": {
                "type": "openai",
                "base_url": "https://example.test/v1",
                "credential_id": "cred-live",
                "supports_image_edit": True,
            },
            "missing": {
                "type": "anthropic",
                "base_url": "https://example.test",
                "credential_id": "cred-missing",
            },
        },
    }


def test_factory_loads_effective_configuration_once_and_injects_live_dependencies(tmp_path):
    loads: list[Path] = []
    transport_calls = []
    transport = MockProviderTransport()

    def load(project_dir):
        loads.append(Path(project_dir))
        return _config()

    def make_transport(models, providers, *, credentials, redactor):
        transport_calls.append((models, providers, credentials, redactor))
        return transport

    context = RuntimeContextFactory(
        config_loader=load,
        secret_store=MemorySecretStore({"cred-live": "sk-secret"}),
        environ={},
        transport_factory=make_transport,
        cache_dir=tmp_path / "cache",
    ).create(tmp_path / "project", tmp_path / "run")

    assert loads == [tmp_path / "project"]
    assert len(transport_calls) == 1
    assert set(context.credentials) == {"live"}
    assert context.offline is False
    assert context.client.state is context.state
    assert context.client.cache is context.cache
    assert context.cache.cache_dir == tmp_path / "cache"
    assert context.state.budget["phase_reasoning"] == 10
    assert context.state.budget["generation"] == 5
    assert context.client.clean_error("failed sk-secret") == "failed ***REDACTED***"


def test_missing_credentials_use_offline_transport_without_bypassing_configuration(tmp_path):
    calls = []

    def should_not_construct(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("live transport must not be constructed")

    context = RuntimeContextFactory(
        config_loader=lambda _project: _config(),
        secret_store=MemorySecretStore(),
        environ={},
        transport_factory=should_not_construct,
        cache_dir=tmp_path / "cache",
    ).create(tmp_path / "project", tmp_path / "run")

    assert context.offline is True
    assert isinstance(context.client.transport, MockProviderTransport)
    assert context.models["image_generate"]["provider"] == "live"
    assert calls == []


def test_factory_uses_the_same_state_adapter_for_new_and_resumed_runs(tmp_path):
    state_calls = []

    def load_state(path, run_id, budget):
        state_calls.append((path, run_id, budget))
        state = RunState(run_id, budget=budget)
        state.mark_step("intake", "completed")
        return state

    context = RuntimeContextFactory(
        config_loader=lambda _project: {"models": {}, "providers": {}},
        state_loader=load_state,
        cache_dir=tmp_path / "cache",
        environ={},
    ).create(tmp_path / "project", tmp_path / "named-run")

    assert len(state_calls) == 1
    assert state_calls[0][0] == tmp_path / "named-run" / "run_state.json"
    assert context.state.step_status("intake") == "completed"
    assert context.store.run_dir == tmp_path / "named-run"


def test_transport_construction_errors_are_redacted(tmp_path):
    def broken_transport(*_args, **_kwargs):
        raise RuntimeError("transport rejected sk-secret")

    factory = RuntimeContextFactory(
        config_loader=lambda _project: _config(),
        secret_store=MemorySecretStore({"cred-live": "sk-secret"}),
        environ={},
        transport_factory=broken_transport,
        cache_dir=tmp_path / "cache",
    )

    with pytest.raises(RuntimeContextError) as raised:
        factory.create(tmp_path / "project", tmp_path / "run")
    assert "sk-secret" not in str(raised.value)
    assert "***REDACTED***" in str(raised.value)


def test_early_configuration_and_late_cache_errors_are_redacted(tmp_path):
    def broken_config(_project):
        raise RuntimeError("config failed with env-secret")

    early = RuntimeContextFactory(
        config_loader=broken_config,
        environ={"OPENAI_API_KEY": "env-secret"},
        cache_dir=tmp_path / "cache",
    )
    with pytest.raises(RuntimeContextError) as early_error:
        early.create(tmp_path / "project", tmp_path / "early-run")
    assert "env-secret" not in str(early_error.value)

    def broken_cache(_path):
        raise RuntimeError("cache failed with keyring-secret")

    late = RuntimeContextFactory(
        config_loader=lambda _project: _config(),
        secret_store=MemorySecretStore({"cred-live": "keyring-secret"}),
        environ={},
        transport_factory=lambda *_args, **_kwargs: MockProviderTransport(),
        cache_factory=broken_cache,
        cache_dir=tmp_path / "cache",
    )
    with pytest.raises(RuntimeContextError) as late_error:
        late.create(tmp_path / "project", tmp_path / "late-run")
    assert "keyring-secret" not in str(late_error.value)
