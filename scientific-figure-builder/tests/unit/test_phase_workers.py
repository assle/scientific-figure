from __future__ import annotations

from figure_tools.orchestrator import PhaseInvocation
from figure_tools.phase_workers import ProviderPhaseWorker, StructuredPhaseWorker
from figure_tools.providers.client import ProviderClient
from figure_tools.providers.transport import MockProviderTransport


def test_provider_phase_worker_uses_fresh_phase_reasoning_call():
    transport = MockProviderTransport()
    client = ProviderClient(
        {"phase_reasoning": {"model": "reasoner"}}, transport,
    )
    worker = ProviderPhaseWorker(client, fallback=StructuredPhaseWorker())
    request = {
        "figure_id": "f1", "panels": [],
        "export_target": None, "figure_width_cm": None,
        "language": None, "style": None,
    }

    artifact = worker.run(PhaseInvocation(
        phase="intake",
        prompt="intake-only prompt",
        prompt_version="1.0",
        context={"user_request": request, "run_id": "r1",
                 "prompt_hash": "sha256:prompt"},
        allowed_tools=("check_figure_requirements",),
    ))

    assert artifact["artifact_type"] == "figure_brief"
    assert transport.calls == [("phase_reasoning", "reasoner")]


def test_planning_worker_returns_advice_without_generation_invariants():
    transport = MockProviderTransport()
    client = ProviderClient(
        {"phase_reasoning": {"model": "reasoner"}}, transport,
    )
    worker = ProviderPhaseWorker(client, fallback=StructuredPhaseWorker())
    request = {
        "figure_id": "f1",
        "canvas": {"aspect_ratio": 2.0, "width": 180, "height": 90},
        "panels": [{
            "panel_id": "p1", "bbox": [0, 0, 1, 1],
            "physical_size": [180, 90],
            "elements": [
                {"element_id": "start", "type": "text", "content": "Start"},
                {"element_id": "finish", "type": "text", "content": "Finish"},
            ],
        }],
        "generation_intent": [{
            "unit_id": "whole", "method": "image_model", "scope": "figure",
        }],
        "export_target": "general", "figure_width_cm": 14,
        "language": "en", "style": "default",
    }
    brief = dict(StructuredPhaseWorker().run(PhaseInvocation(
        phase="intake", prompt="intake", prompt_version="1.0",
        context={"user_request": request, "run_id": "r1", "prompt_hash": "sha256:p"},
        allowed_tools=("check_figure_requirements",),
    )))

    artifact = worker.run(PhaseInvocation(
        phase="planning", prompt="planning", prompt_version="1.0",
        context={"figure_brief": brief, "default_canvas": None, "revision": 1},
        allowed_tools=("create_figure_plan",),
    ))

    assert artifact["artifact_type"] == "planning_advice"
    assert set(artifact) == {
        "schema_version", "artifact_type", "asset_hints", "composition",
        "style_bible",
    }
    assert not ({
        "generation_units", "generation_intent_hash", "assets", "routing",
    } & set(artifact))
    fallback = transport.requests[-1]["payload"]["fallback_artifact"]
    assert fallback == artifact
