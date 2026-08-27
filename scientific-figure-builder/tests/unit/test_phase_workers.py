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
