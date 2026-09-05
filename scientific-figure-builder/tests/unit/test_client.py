"""Provider client tests: budget, cache, secrets, rate-limit, analysis, validation.

All tests use MockProviderTransport - no paid calls (plan section 15, Phase 4).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from figure_tools.providers.auth import (
    CredentialResolver,
    KeyringSecretStore,
    MemorySecretStore,
    SecretRedactor,
    credential_status,
    new_credential_id,
    get_api_key,
    redact,
)
from figure_tools.providers.client import ProviderClient
from figure_tools.providers.generic_transport import OpenAICompatibleTransport
from figure_tools.providers.transport import MockProviderTransport
from figure_tools.state import BudgetExceeded, Cache, RunState

MODELS = {
    "image_generate": {"model": "ep-gen"},
    "image_edit": {"model": "ep-edit"},
    "vision_analyze": {"model": "ep-analyze"},
    "vision_validate": {"model": "ep-validate"},
}
BUDGET = {"reference_analysis": 1, "generation": 2, "edits": 1,
          "validations": 2, "final_validation": 1}


def _client(tmp_path: Path, transport=None, api_key=None, state=None, cache=None):
    transport = transport or MockProviderTransport()
    state = state or RunState("run-1", budget=BUDGET)
    cache = cache or Cache(tmp_path / "cache")
    client = ProviderClient(MODELS, transport, api_key=api_key, state=state,
                            cache=cache, output_dir=tmp_path)
    return client, state, cache


def _save_png(path: Path, mode="RGB", size=(64, 64), color=(255, 255, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)


def _save_rgba(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(img).ellipse((384, 384, 640, 640), fill=(200, 40, 40, 255))
    img.save(path)


# --- auth ----------------------------------------------------------------
def test_get_api_key_from_env(monkeypatch):
    monkeypatch.setenv("SCIENTIFIC_FIGURE_API_KEY", "sk-test")
    assert get_api_key() == "sk-test"


def test_redact_replaces_key():
    assert redact("hello sk-test world", "sk-test") == "hello ***REDACTED*** world"


def test_credential_resolver_uses_configured_environment_name(monkeypatch):
    monkeypatch.setenv("CUSTOM_PROVIDER_KEY", "custom-secret")
    resolved = CredentialResolver().resolve(
        "custom", {"type": "openai", "key_env": "CUSTOM_PROVIDER_KEY"}
    )
    assert resolved is not None
    assert resolved.value == "custom-secret"
    assert resolved.source == "environment"
    assert resolved.key_env == "CUSTOM_PROVIDER_KEY"


def test_credential_resolver_derives_legacy_environment_name(monkeypatch):
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-secret")
    resolved = CredentialResolver().resolve("custom", {"type": "openai"})
    assert resolved is not None
    assert resolved.value == "custom-secret"
    assert resolved.key_env == "CUSTOM_API_KEY"


def test_secret_redactor_handles_multiple_credentials_and_exceptions():
    redactor = SecretRedactor(["first-secret", "second-secret"])
    message = redactor.redact_text("first-secret/second-secret")
    assert message == "***REDACTED***/***REDACTED***"
    error = RuntimeError("second-secret failed")
    assert redactor.safe_exception(error) == "RuntimeError: ***REDACTED*** failed"


def test_keyring_credential_wins_over_environment(monkeypatch):
    credential_id = new_credential_id()
    store = MemorySecretStore({credential_id: "keyring-secret"})
    monkeypatch.setenv("CUSTOM_PROVIDER_KEY", "environment-secret")
    resolved = CredentialResolver(store).resolve(
        "custom", {
            "type": "openai", "key_env": "CUSTOM_PROVIDER_KEY",
            "credential_id": credential_id,
        }
    )
    assert resolved is not None
    assert resolved.value == "keyring-secret"
    assert resolved.source == "keyring"
    assert credential_status(resolved) == {
        "configured": True, "source": "keyring",
        "credential_id": credential_id, "key_env": "CUSTOM_PROVIDER_KEY",
    }


def test_keyring_read_failure_falls_back_without_secret_in_warning(monkeypatch):
    class BrokenStore(MemorySecretStore):
        def get(self, credential_id):
            raise RuntimeError("backend echoed environment-secret")

    monkeypatch.setenv("CUSTOM_PROVIDER_KEY", "environment-secret")
    resolver = CredentialResolver(BrokenStore())
    resolved = resolver.resolve(
        "custom", {"type": "openai", "key_env": "CUSTOM_PROVIDER_KEY",
                    "credential_id": new_credential_id()}
    )
    assert resolved is not None and resolved.value == "environment-secret"
    assert resolver.last_warning is not None
    assert "environment-secret" not in str(resolver.last_warning)


def test_keyring_adapter_uses_fixed_service_and_translates_backend_errors():
    class Backend:
        def __init__(self):
            self.calls = []

        def get_password(self, service, user):
            self.calls.append(("get", service, user))
            return "secret"

        def set_password(self, service, user, value):
            self.calls.append(("set", service, user, value))

        def delete_password(self, service, user):
            self.calls.append(("delete", service, user))

    backend = Backend()
    store = KeyringSecretStore(backend=backend)
    store.set("id", "secret")
    assert store.get("id") == "secret"
    store.delete("id")
    assert all(call[1] == "scientific-figure-builder" for call in backend.calls)


# --- generation ----------------------------------------------------------
def test_generate_produces_transparent_image(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    out = tmp_path / "asset.png"
    meta = client.generate_image_asset("a red circle", {"size": "1024x1024"}, output_path=out)
    assert out.is_file()
    img = Image.open(out)
    assert "A" in img.getbands()
    assert meta["transparent"] is True
    assert meta["model"] == "ep-gen"
    assert meta["prompt_hash"].startswith("sha256:")
    assert meta["cached"] is False
    assert meta["pixel_dimensions"] == [2048, 2048]


def test_generate_cache_hit_no_second_call(tmp_path: Path):
    client, state, _ = _client(tmp_path)
    out1 = tmp_path / "a1.png"
    out2 = tmp_path / "a2.png"
    client.generate_image_asset("red circle", {"size": "1024"}, output_path=out1)
    calls_after_first = len(client.transport.calls)
    client.generate_image_asset("red circle", {"size": "1024"}, output_path=out2)
    assert len(client.transport.calls) == calls_after_first
    assert state.cache_hits == 1
    assert out1.read_bytes() == out2.read_bytes()


def test_generate_transmits_reference_roles_through_transport_seam(tmp_path: Path):
    transport = MockProviderTransport()
    client, _, _ = _client(tmp_path, transport=transport)
    reference = tmp_path / "style.png"
    _save_png(reference)

    client.generate_image_asset(
        "red circle",
        {},
        output_path=tmp_path / "asset.png",
        reference_hashes=["sha256:style"],
        reference_paths=[str(reference)],
        reference_descriptors=[{"role": "style", "strength": 0.75}],
    )

    assert transport.requests[-1]["payload"]["references"] == [
        {"role": "style", "strength": 0.75}
    ]
    assert transport.requests[-1]["image_paths"] == [str(reference)]


def test_generate_respects_budget(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    out = tmp_path / "a.png"
    client.generate_image_asset("p1", {}, output_path=out, force=True)
    client.generate_image_asset("p2", {}, output_path=out, force=True)
    with pytest.raises(BudgetExceeded):
        client.generate_image_asset("p3", {}, output_path=out, force=True)


# --- analysis ------------------------------------------------------------
def test_analyze_returns_structured(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    ref = tmp_path / "ref.png"
    _save_png(ref)
    result = client.analyze_reference_figure(ref, prompt="describe panels")
    for key in ("panels", "objects", "text_candidates", "confidence", "uncertainties"):
        assert key in result


def test_analyze_cache_hit(tmp_path: Path):
    client, state, _ = _client(tmp_path)
    ref = tmp_path / "ref.png"
    _save_png(ref)
    client.analyze_reference_figure(ref)
    n = len(client.transport.calls)
    client.analyze_reference_figure(ref)
    assert len(client.transport.calls) == n
    assert state.cache_hits == 1


def test_analyze_respects_budget(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    ref = tmp_path / "ref.png"
    _save_png(ref)
    client.analyze_reference_figure(ref, force=True)
    with pytest.raises(BudgetExceeded):
        client.analyze_reference_figure(ref, force=True)


def test_reference_analysis_expands_output_budget_until_response_is_complete(tmp_path: Path):
    output_limits = []

    class Response:
        def __init__(self, body):
            self.body = io.BytesIO(json.dumps(body).encode("utf-8"))

        def read(self):
            return self.body.read()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request):
        limit = int(json.loads(request.data)["max_output_tokens"])
        output_limits.append(limit)
        if limit < 16384:
            return Response({
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output_text": '{"panels":[',
            })
        return Response({
            "status": "completed",
            "output_text": json.dumps({
                "panels": [], "objects": [], "text_candidates": [],
                "confidence": 0.9, "uncertainties": [],
            }),
        })

    transport = OpenAICompatibleTransport(
        "vision",
        {"type": "openai", "base_url": "https://models.example/v1"},
        credential="test-key",
        opener=opener,
    )
    state = RunState("run-1", budget={"reference_analysis": 3})
    client, _, _ = _client(tmp_path, transport=transport, state=state)
    reference = tmp_path / "reference.png"
    _save_png(reference)

    result = client.analyze_reference_figure(reference, force=True)

    assert result["confidence"] == 0.9
    assert output_limits == [4096, 8192, 16384]
    assert state.calls_used("reference_analysis") == 3
    expansions = [
        event for event in state.to_dict()["audit_log"]
        if event["event"] == "structured_output_expanded"
    ]
    assert [event["details"]["next_max_output_tokens"] for event in expansions] == [
        8192, 16384,
    ]


def test_reference_analysis_expansion_stops_before_exceeding_call_budget(tmp_path: Path):
    requests = []

    class Response:
        def __init__(self):
            self.body = io.BytesIO(json.dumps({
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output_text": '{"panels":[',
            }).encode("utf-8"))

        def read(self):
            return self.body.read()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request):
        requests.append(request)
        return Response()

    transport = OpenAICompatibleTransport(
        "vision",
        {"type": "openai", "base_url": "https://models.example/v1"},
        credential="test-key",
        opener=opener,
    )
    state = RunState("run-1", budget={"reference_analysis": 1})
    client, _, _ = _client(tmp_path, transport=transport, state=state)
    reference = tmp_path / "reference.png"
    _save_png(reference)

    with pytest.raises(BudgetExceeded, match="reference_analysis"):
        client.analyze_reference_figure(reference, force=True)

    assert len(requests) == 1
    assert state.calls_used("reference_analysis") == 1
    assert state.to_dict()["audit_log"] == []


# --- rate limit ----------------------------------------------------------
def test_rate_limit_retry_succeeds(tmp_path: Path):
    transport = MockProviderTransport(fail_once_roles={"generation"})
    client, state, _ = _client(tmp_path, transport=transport)
    out = tmp_path / "a.png"
    client.generate_image_asset("p", {}, output_path=out)
    assert out.is_file()
    assert state.retries("generation", "transient") >= 1


# --- secrets -------------------------------------------------------------
def test_secrets_never_in_artifacts(tmp_path: Path):
    client, _, _ = _client(tmp_path, api_key="sk-secret-XYZ")
    out = tmp_path / "a.png"
    client.generate_image_asset("p", {}, output_path=out)
    client._log_prompt("generation", "p")  # exercise prompt logging
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert b"sk-secret-XYZ" not in f.read_bytes(), f"secret leaked in {f}"


# --- upload disclosure ---------------------------------------------------
def test_upload_disclosure(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    ref = tmp_path / "ref.png"
    _save_png(ref)
    disclosure = client.disclose_uploads([ref])
    assert len(disclosure) == 1
    assert disclosure[0]["path"] == str(ref)
    assert disclosure[0]["content_hash"].startswith("sha256:")


# --- validation ----------------------------------------------------------
def test_validate_image_asset_combines_checks(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    img = tmp_path / "a.png"
    _save_rgba(img)
    report = client.validate_image_asset(img, physical_size_mm=(80, 80))
    check_ids = {c["check_id"] for c in report["checks"]}
    assert "alpha_channel" in check_ids  # deterministic
    assert "multimodal_semantic" in check_ids  # from provider
    assert report["summary"]["blocking"] is False


def test_validate_report_conforms_to_schema(tmp_path: Path):
    from jsonschema import Draft202012Validator

    from figure_tools._resources import schema_path

    client, _, _ = _client(tmp_path)
    img = tmp_path / "a.png"
    _save_rgba(img)
    report = client.validate_image_asset(img, physical_size_mm=(80, 80))
    schema = json.loads(schema_path("validation-report.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(report))


def test_validate_detects_missing_alpha(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    img = tmp_path / "a.png"
    _save_png(img, mode="RGB")  # no alpha
    report = client.validate_image_asset(img, physical_size_mm=(80, 80))
    assert report["summary"]["blocking"] is True


def test_edit_produces_child_with_parent(tmp_path: Path):
    from figure_tools.provenance import hash_file

    client, _, _ = _client(tmp_path)
    parent = tmp_path / "parent.png"
    _save_rgba(parent)
    out = tmp_path / "edited.png"
    meta = client.edit_image_asset(parent, "brighten", {}, output_path=out,
                                   parent_asset_id="asset-1")
    assert out.is_file()
    assert meta["parent_asset_id"] == "asset-1"
    assert meta["reference_hashes"] == [hash_file(parent)]


def test_edit_includes_mask_in_cache_identity_and_transport(tmp_path: Path):
    from figure_tools.provenance import hash_file

    transport = MockProviderTransport()
    client, _, _ = _client(tmp_path, transport=transport)
    parent = tmp_path / "parent.png"
    mask = tmp_path / "mask.png"
    _save_rgba(parent)
    _save_rgba(mask)

    meta = client.edit_image_asset(
        parent,
        "fix receptor",
        {},
        output_path=tmp_path / "edited.png",
        parent_asset_id="asset-1",
        mask_path=mask,
    )

    assert meta["reference_hashes"] == [hash_file(parent), hash_file(mask)]
    assert transport.requests[-1]["image_paths"] == [str(parent), str(mask)]


def test_edit_reuses_generation_model_when_override_is_absent(tmp_path: Path):
    models = {key: value for key, value in MODELS.items() if key != "image_edit"}
    transport = MockProviderTransport()
    client = ProviderClient(
        models,
        transport,
        state=RunState("run-1", budget=BUDGET),
        cache=Cache(tmp_path / "cache"),
        output_dir=tmp_path,
    )
    parent = tmp_path / "parent.png"
    _save_rgba(parent)

    meta = client.edit_image_asset(
        parent, "make it blue", {}, output_path=tmp_path / "edited.png",
    )

    assert meta["model"] == "ep-gen"
    assert transport.calls == [("edits", "ep-gen")]


def test_edit_without_override_consumes_generation_budget(tmp_path: Path):
    models = {key: value for key, value in MODELS.items() if key != "image_edit"}
    client = ProviderClient(
        models,
        MockProviderTransport(),
        state=RunState("run-1", budget={"generation": 0}),
        cache=Cache(tmp_path / "cache"),
        output_dir=tmp_path,
    )
    parent = tmp_path / "parent.png"
    _save_rgba(parent)

    with pytest.raises(BudgetExceeded, match="generation"):
        client.edit_image_asset(
            parent, "make it blue", {}, output_path=tmp_path / "edited.png",
        )
