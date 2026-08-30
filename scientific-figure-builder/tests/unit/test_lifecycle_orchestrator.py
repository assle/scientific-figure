"""Public lifecycle-orchestrator seam tests.

These tests observe phase results and persisted artifacts rather than private
workflow helpers or the prose of phase prompts.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from figure_tools.orchestrator import FigureOrchestrator, PhaseInvocation
from figure_tools.provenance import hash_json
from figure_tools.providers.client import ProviderClient
from figure_tools.providers.transport import MockProviderTransport
from figure_tools.phase_workers import StructuredPhaseWorker
from figure_tools.state import BudgetExceeded, Cache, RunDirectory, RunState
from figure_tools._resources import schema_path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


MODELS = {
    "image_generate": {"model": "ep-gen"},
    "image_edit": {"model": "ep-edit"},
    "vision_analyze": {"model": "ep-analyze"},
    "vision_validate": {"model": "ep-validate"},
}
BUDGET = {"reference_analysis": 1, "generation": 5, "edits": 2,
          "validations": 5, "final_validation": 5}


class RecordingWorker:
    def __init__(self) -> None:
        self.invocations: list[PhaseInvocation] = []
        self.delegate = StructuredPhaseWorker()

    def run(self, invocation: PhaseInvocation) -> dict:
        self.invocations.append(invocation)
        return dict(self.delegate.run(invocation))


class BriefProducingWorker:
    def run(self, invocation: PhaseInvocation) -> dict:
        if invocation.phase != "intake":
            return {}
        request = invocation.context["user_request"]
        return {
            "schema_version": "1.0",
            "artifact_type": "figure_brief",
            "brief_id": f"{request['figure_id']}-brief-worker",
            "figure_id": request["figure_id"],
            "run_id": "worker-run",
            "request": request,
            "intent": "worker-produced",
            "inputs": {"reference_figures": [], "data_sources": []},
            "delivery": {},
            "language": None,
            "style": None,
            "assumptions": [],
            "uncertainties": [],
            "required_clarifications": [
                {"field": "language", "question": "Choose language", "default": "zh"}
            ],
            "status": "draft",
            "provenance": {
                "phase": "intake", "prompt_version": invocation.prompt_version,
                "prompt_hash": "sha256:worker", "request_hash": "sha256:request",
            },
        }


class BlankEditTransport(MockProviderTransport):
    def _response(self, role, model, payload):
        if role == "edits":
            image = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return {"image_bytes": buffer.getvalue(), "model": model, "seed": 0}
        return super()._response(role, model, payload)


class SemanticRegressionEditTransport(MockProviderTransport):
    def __init__(self) -> None:
        super().__init__()
        self.regression_pending = False

    def _response(self, role, model, payload):
        if role == "edits":
            self.regression_pending = True
            image = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
            from PIL import ImageDraw
            ImageDraw.Draw(image).ellipse(
                (768, 768, 1280, 1280), fill=(40, 80, 220, 255)
            )
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return {"image_bytes": buffer.getvalue(), "model": model, "seed": 0}
        if role == "final_validation" and self.regression_pending:
            self.regression_pending = False
            return {"checks": [{
                "check_id": "global_consistency_regression",
                "scope": "final",
                "level": "error",
                "status": "fail",
                "detail": "global scientific semantics regressed",
            }], "blocking": True}
        return super()._response(role, model, payload)


def _request(**over):
    base = {
        "figure_id": "figure-01",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": [
            {"panel_id": "a", "bbox": [0, 0, 0.5, 1], "physical_size": [90, 112.5],
             "elements": [{"element_id": "curve", "type": "data_plot",
                           "plot_spec": str(FIXTURES / "plot_spec_line.json")}]},
            {"panel_id": "b", "bbox": [0.5, 0, 0.5, 1], "physical_size": [90, 112.5],
             "elements": [{"element_id": "fiber", "type": "image_asset",
                           "prompt": "optical fiber cross-section"}]},
        ],
        "labels": [{"element_id": "label-a", "kind": "label", "content": "(a) Coupling"}],
        "assumptions": ["Gaussian beam approximation."],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "auto_execute": True,
    }
    base.update(over)
    return base


def _orchestrator(
    tmp_path: Path,
    request: dict | None,
    worker=None,
    *,
    run_dir: Path | None = None,
    state: RunState | None = None,
    transport=None,
):
    run_dir = run_dir or RunDirectory(base_dir=tmp_path).create(request["figure_id"])
    transport = transport or MockProviderTransport()
    state = state or RunState(run_id=run_dir.name, budget=BUDGET)
    client = ProviderClient(MODELS, transport, state=state,
                            cache=Cache(run_dir / "cache"), output_dir=run_dir)
    return FigureOrchestrator(
        request=request,
        config={},
        run_dir=run_dir,
        provider_client=client,
        state=state,
        base_dir=ROOT,
        worker=worker,
    ), run_dir, client


def _mark_validation_failed(run_dir: Path, validation: dict, check_id: str) -> None:
    check = next(item for item in validation["checks"] if item["check_id"] == check_id)
    check["status"] = "fail"
    check["level"] = "error"
    validation["summary"]["errors"] += 1
    validation["summary"]["blocking"] = True
    (run_dir / "validation" / "final.json").write_text(
        json.dumps(validation), encoding="utf-8"
    )


def test_start_returns_clarification_next_action_without_paid_work(tmp_path: Path):
    worker = RecordingWorker()
    request = _request(export_target=None, figure_width_cm=None,
                       language=None, style=None)
    orchestrator, run_dir, client = _orchestrator(tmp_path, request, worker)

    result = orchestrator.advance()

    assert result["phase"] == "intake"
    assert result["status"] == "paused"
    assert result["next_action"] == "submit_clarifications"
    assert {item["field"] for item in result["clarifications"]} == {
        "export_target", "figure_width_cm", "language", "style",
    }
    assert (run_dir / "plans" / "figure_brief.json").is_file()
    assert not client.transport.calls
    assert worker.invocations[0].phase == "intake"
    assert "generate_image_asset" not in worker.invocations[0].allowed_tools


def test_user_can_submit_clarifications_and_continue_from_draft_brief(tmp_path: Path):
    request = _request(export_target=None, figure_width_cm=None,
                       language=None, style=None)
    orchestrator, run_dir, _ = _orchestrator(tmp_path, request)
    paused = orchestrator.advance()
    assert paused["next_action"] == "submit_clarifications"

    completed = orchestrator.advance({
        "action": "submit_clarifications",
        "answers": {
            "export_target": "general",
            "figure_width_cm": 14.0,
            "language": "en",
            "style": "default",
        },
    })

    assert completed["status"] == "completed"
    brief = json.loads((run_dir / "plans" / "figure_brief.json").read_text())
    assert brief["status"] == "ready"
    assert brief["required_clarifications"] == []
    assert brief["delivery"]["figure_width_cm"] == 14.0


def test_intake_persists_the_phase_worker_artifact(tmp_path: Path):
    request = _request(export_target=None, figure_width_cm=None,
                       language=None, style=None)
    orchestrator, run_dir, _ = _orchestrator(
        tmp_path, request, BriefProducingWorker()
    )

    result = orchestrator.advance()

    assert result["phase"] == "intake"
    brief = json.loads((run_dir / "plans" / "figure_brief.json").read_text())
    assert brief["intent"] == "worker-produced"
    assert brief["brief_id"].endswith("brief-worker")


def test_figure_brief_is_schema_valid_and_carries_resolved_delivery(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())

    result = orchestrator.advance()

    assert result["status"] == "completed"
    brief = json.loads((run_dir / "plans" / "figure_brief.json").read_text())
    schema = json.loads(schema_path("figure-brief.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(brief))
    assert brief["status"] == "ready"
    assert brief["delivery"] == {"export_target": "general", "figure_width_cm": 14.0}
    assert brief["language"] == "en"
    assert brief["style"] == "default"
    assert brief["request"]["figure_id"] == "figure-01"


def test_figure_plan_is_schema_valid_and_references_the_brief(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())

    result = orchestrator.advance()

    assert result["status"] == "completed"
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    schema = json.loads(schema_path("figure-plan.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(plan))
    brief = json.loads((run_dir / "plans" / "figure_brief.json").read_text())
    assert plan["brief_ref"]["content_hash"] == hash_json(brief)


def test_execution_result_is_schema_valid_and_references_the_plan(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())

    result = orchestrator.advance()

    assert result["status"] == "completed"
    execution = json.loads((run_dir / "plans" / "execution_result.json").read_text())
    schema = json.loads(schema_path("execution-result.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(execution))
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    assert execution["plan_ref"]["content_hash"] == hash_json(plan)
    assert execution["assembly"]["content_hash"].startswith("sha256:")
    assert execution["plots"]["content_hash"].startswith("sha256:")
    assert execution["vectors"]["content_hash"].startswith("sha256:")
    assert execution["layout_manifests"]
    assert execution["call_provenance"]["counts"]["generation"] == 1


def test_export_result_is_versioned_and_references_validation_and_assembly(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())

    orchestrator.advance()

    export_result = json.loads((run_dir / "plans" / "export_result.json").read_text())
    schema = json.loads(schema_path("export-result.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(export_result))
    validation = json.loads((run_dir / "validation" / "final.json").read_text())
    assert export_result["validation_ref"]["content_hash"] == hash_json(validation)
    assert export_result["assembly_ref"]["content_hash"].startswith("sha256:")
    assert export_result["forced"] is False


def test_changed_figure_brief_cannot_reuse_an_old_plan(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())
    orchestrator.advance()
    brief_path = run_dir / "plans" / "figure_brief.json"
    brief = json.loads(brief_path.read_text())
    brief["language"] = "zh"
    brief_path.write_text(json.dumps(brief), encoding="utf-8")

    result = orchestrator.advance("resume")

    assert result["status"] == "completed"
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    assert plan["brief_ref"]["content_hash"] == hash_json(brief)


def test_externally_revised_plan_invalidates_execution_before_resume(tmp_path: Path):
    orchestrator, run_dir, client = _orchestrator(tmp_path, _request())
    assert orchestrator.advance()["status"] == "completed"
    generation_calls = client.state.calls_used("generation")
    client.cache = None
    plan_path = run_dir / "plans" / "figure_plan.json"
    plan = json.loads(plan_path.read_text())
    plan["canvas"]["width"] += 1
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    resumed = orchestrator.advance("resume")

    assert resumed["status"] == "completed"
    assert client.state.calls_used("generation") == generation_calls
    revised_plan = json.loads(plan_path.read_text())
    assert revised_plan["revision"] == 2
    assert (run_dir / "plans" / "figure_plan.v2.json").is_file()
    execution = json.loads(
        (run_dir / "plans" / "execution_result.json").read_text()
    )
    assert execution["plan_ref"]["content_hash"] == hash_json(revised_plan)


def test_completed_resume_repairs_changed_export_without_provider_calls(tmp_path: Path):
    orchestrator, run_dir, client = _orchestrator(tmp_path, _request())
    assert orchestrator.advance()["status"] == "completed"
    exported = run_dir / "exports" / "figure.png"
    exported.write_bytes(b"corrupt export")
    calls_before = list(client.transport.calls)

    resumed = orchestrator.advance("resume")

    assert resumed["status"] == "completed"
    assert exported.read_bytes() == (run_dir / "assembly" / "figure.png").read_bytes()
    assert client.transport.calls == calls_before


def test_completed_resume_restores_a_changed_paid_asset_from_cache(tmp_path: Path):
    orchestrator, run_dir, client = _orchestrator(tmp_path, _request())
    assert orchestrator.advance()["status"] == "completed"
    asset = run_dir / "assets" / "fiber.png"
    asset.write_bytes(b"corrupt raster")
    generation_before = client.state.calls_used("generation")

    resumed = orchestrator.advance("resume")

    assert resumed["status"] == "completed"
    assert asset.read_bytes() != b"corrupt raster"
    assert client.state.calls_used("generation") == generation_before


def test_resume_completed_run_reuses_artifacts_without_provider_calls(tmp_path: Path):
    orchestrator, run_dir, client = _orchestrator(tmp_path, _request())
    first = orchestrator.advance()
    assert first["status"] == "completed"
    calls_before = list(client.transport.calls)
    persisted = RunState.load(run_dir / "run_state.json")
    resumed_worker = RecordingWorker()
    resumed, _, resumed_client = _orchestrator(
        tmp_path, None, resumed_worker, run_dir=run_dir, state=persisted
    )
    resumed_result = resumed.advance("resume")

    assert resumed_result["status"] == "completed"
    assert client.transport.calls == calls_before
    assert resumed_client.transport.calls == []
    assert resumed_worker.invocations == []


def test_resume_after_execution_reuses_execution_artifacts(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())
    orchestrator.advance()
    state = RunState.load(run_dir / "run_state.json")
    state.clear_step("review_and_repair")
    state.clear_step("export")
    state.clear_artifact("validation_report")
    state.clear_artifact("exports")
    state.save(run_dir / "run_state.json")
    for path in (run_dir / "exports").glob("*"):
        path.unlink()

    resumed_worker = RecordingWorker()
    resumed, _, resumed_client = _orchestrator(
        tmp_path, None, resumed_worker, run_dir=run_dir, state=state
    )

    result = resumed.advance("resume")

    assert result["status"] == "completed"
    assert resumed_client.transport.calls == []
    assert [item.phase for item in resumed_worker.invocations] == ["review_and_repair"]


def test_resume_after_review_reuses_review_artifact(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())
    orchestrator.advance()
    state = RunState.load(run_dir / "run_state.json")
    state.clear_step("export")
    state.clear_artifact("export_result")
    state.clear_artifact("exports")
    state.save(run_dir / "run_state.json")
    for path in (run_dir / "exports").glob("*"):
        path.unlink()
    export_result_path = run_dir / "plans" / "export_result.json"
    if export_result_path.exists():
        export_result_path.unlink()

    resumed_worker = RecordingWorker()
    resumed, _, resumed_client = _orchestrator(
        tmp_path, None, resumed_worker, run_dir=run_dir, state=state
    )

    result = resumed.advance("resume")

    assert result["status"] == "completed"
    assert resumed_client.transport.calls == []
    assert resumed_worker.invocations == []


def test_run_state_persists_phase_and_artifact_references(tmp_path: Path):
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request())

    orchestrator.advance()

    state = json.loads((run_dir / "run_state.json").read_text())
    assert state["current_phase"] == "export"
    assert {"figure_brief", "figure_plan", "execution_result",
            "validation_report", "exports"} <= set(state["artifacts"])


def test_review_writes_schema_valid_repair_plan_on_blocking_validation(tmp_path: Path):
    request = _request()
    request["panels"][0]["elements"][0]["plot_spec"] = str(
        FIXTURES / "does_not_exist.json"
    )
    orchestrator, run_dir, _ = _orchestrator(tmp_path, request)

    result = orchestrator.advance()

    assert result["phase"] == "review_and_repair"
    assert result["status"] == "paused"
    assert result["next_action"] == "repair_required"
    repair = json.loads((run_dir / "plans" / "repair_plan.json").read_text())
    schema = json.loads(schema_path("repair-plan.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(repair))
    assert repair["repairs"][0]["asset_id"] == "curve"
    assert repair["repairs"][0]["route"] == "python"


def test_deterministic_repair_rerenders_source_and_reaches_export(tmp_path: Path):
    request = _request()
    request["panels"][0]["elements"][0]["plot_spec"] = str(
        FIXTURES / "does_not_exist.json"
    )
    orchestrator, run_dir, client = _orchestrator(tmp_path, request)
    paused = orchestrator.advance()
    assert paused["next_action"] == "repair_required"
    generation_calls = client.state.calls_used("generation")
    raster_asset = run_dir / "assets" / "fiber.png"
    raster_asset.write_bytes(b"corrupt unrelated raster")
    unrelated_marker = run_dir / "assets" / "unrelated.marker"
    unrelated_marker.write_text("preserve", encoding="utf-8")

    repaired = orchestrator.advance({
        "action": "apply_repair",
        "repairs": [{
            "asset_id": "curve",
            "route": "python",
            "plot_spec": str(FIXTURES / "plot_spec_line.json"),
        }],
    })

    assert repaired["status"] == "completed"
    assert client.state.calls_used("generation") == generation_calls
    assert raster_asset.read_bytes() != b"corrupt unrelated raster"
    assert (run_dir / "plots" / "curve" / "plot.png").is_file()
    assert (run_dir / "plans" / "layout_analysis.json").is_file()
    assert (run_dir / "exports" / "figure.png").is_file()
    assert not (run_dir / "plans" / "repair_plan.json").exists()
    assert unrelated_marker.read_text(encoding="utf-8") == "preserve"
    revised_plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    assert revised_plan["revision"] == 2
    assert (run_dir / "plans" / "figure_plan.v1.json").is_file()
    assert (run_dir / "plans" / "figure_plan.v2.json").is_file()


def test_deterministic_repair_rejects_raster_edit_route(tmp_path: Path):
    request = _request()
    request["panels"][0]["elements"][0]["plot_spec"] = str(
        FIXTURES / "does_not_exist.json"
    )
    orchestrator, _, _ = _orchestrator(tmp_path, request)
    orchestrator.advance()

    with pytest.raises(ValueError, match="deterministic assets cannot use image_edit"):
        orchestrator.advance({
            "action": "apply_repair",
            "repairs": [{"asset_id": "curve", "route": "image_edit",
                         "plot_spec": str(FIXTURES / "plot_spec_line.json")}],
        })


def test_repair_loop_stops_after_two_quality_retries(tmp_path: Path):
    request = _request()
    missing = str(FIXTURES / "does_not_exist.json")
    request["panels"][0]["elements"][0]["plot_spec"] = missing
    orchestrator, _, _ = _orchestrator(tmp_path, request)
    orchestrator.advance()
    repair = {
        "action": "apply_repair",
        "repairs": [{"asset_id": "curve", "route": "python", "plot_spec": missing}],
    }

    assert orchestrator.advance(repair)["next_action"] == "repair_required"
    assert orchestrator.advance(repair)["next_action"] == "repair_required"
    with pytest.raises(BudgetExceeded, match="quality retries.*exceeded 2"):
        orchestrator.advance(repair)


def test_raster_repair_uses_image_edit_and_reuses_edited_asset(tmp_path: Path):
    orchestrator, run_dir, client = _orchestrator(tmp_path, _request())
    completed = orchestrator.advance()
    assert completed["status"] == "completed"
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    execution = json.loads((run_dir / "plans" / "execution_result.json").read_text())
    validation = json.loads((run_dir / "validation" / "final.json").read_text())
    _mark_validation_failed(run_dir, validation, "multimodal_semantic")
    repair_plan = {
        "schema_version": "1.0",
        "artifact_type": "repair_plan",
        "run_id": client.state.run_id,
        "plan_ref": {"artifact": "plans/figure_plan.json",
                      "content_hash": hash_json(plan)},
        "execution_ref": {"artifact": "plans/execution_result.json",
                          "content_hash": hash_json(execution)},
        "validation_ref": {"artifact": "validation/final.json",
                           "content_hash": hash_json(validation)},
        "repairs": [{"asset_id": "fiber", "route": "image_edit",
                     "action": "make the asset blue", "source_check": "multimodal_semantic",
                     "status": "pending"}],
        "status": "pending",
    }
    (run_dir / "plans" / "repair_plan.json").write_text(
        json.dumps(repair_plan), encoding="utf-8"
    )
    calls_before = len(client.transport.calls)
    unrelated_marker = run_dir / "plots" / "curve" / "unrelated.marker"
    unrelated_marker.write_text("preserve", encoding="utf-8")

    repaired = orchestrator.advance({
        "action": "apply_repair",
        "repairs": [{"asset_id": "fiber", "route": "image_edit",
                     "prompt": "make the asset blue"}],
    })

    assert repaired["status"] == "completed"
    new_roles = [role for role, _ in client.transport.calls[calls_before:]]
    assert "edits" in new_roles
    assert "generation" not in new_roles
    manifest = json.loads((run_dir / "asset_manifest.json").read_text())
    fiber = next(asset for asset in manifest["assets"] if asset["asset_id"] == "fiber")
    assert fiber["parent_asset_id"] == "fiber"
    assert unrelated_marker.read_text(encoding="utf-8") == "preserve"


def test_raster_edit_rolls_back_when_the_edited_asset_fails_hard_checks(tmp_path: Path):
    transport = BlankEditTransport()
    orchestrator, run_dir, client = _orchestrator(
        tmp_path, _request(), transport=transport,
    )
    assert orchestrator.advance()["status"] == "completed"
    parent_path = run_dir / "assets" / "fiber.png"
    original_hash = hash_json({"bytes": parent_path.read_bytes().hex()})
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    execution = json.loads((run_dir / "plans" / "execution_result.json").read_text())
    validation = json.loads((run_dir / "validation" / "final.json").read_text())
    _mark_validation_failed(run_dir, validation, "multimodal_semantic")
    repair_plan = {
        "schema_version": "1.0",
        "artifact_type": "repair_plan",
        "run_id": client.state.run_id,
        "plan_ref": {"artifact": "plans/figure_plan.json",
                     "content_hash": hash_json(plan)},
        "execution_ref": {"artifact": "plans/execution_result.json",
                         "content_hash": hash_json(execution)},
        "validation_ref": {"artifact": "validation/final.json",
                          "content_hash": hash_json(validation)},
        "repairs": [{
            "asset_id": "fiber",
            "route": "image_edit",
            "operation": "raster_edit",
            "action": "fix the receptor",
            "source_check": "multimodal_semantic",
            "status": "pending",
        }],
        "status": "pending",
    }
    (run_dir / "plans" / "repair_plan.json").write_text(
        json.dumps(repair_plan), encoding="utf-8"
    )
    generation_before = client.state.calls_used("generation")

    result = orchestrator.advance({
        "action": "apply_repair",
        "repairs": [{
            "asset_id": "fiber",
            "operation": "raster_edit",
            "prompt": "fix the receptor",
        }],
    })

    assert result["status"] == "completed"
    assert client.state.calls_used("generation") == generation_before
    assert hash_json({"bytes": parent_path.read_bytes().hex()}) == original_hash
    outcome = json.loads(
        (run_dir / "validation" / "edit_outcomes" / "fiber.json").read_text()
    )
    assert outcome["status"] == "rolled_back"
    assert outcome["reason"] == "edited asset failed Deterministic checks"


def test_raster_edit_rolls_back_when_global_validation_regresses(tmp_path: Path):
    transport = SemanticRegressionEditTransport()
    orchestrator, run_dir, client = _orchestrator(
        tmp_path, _request(), transport=transport,
    )
    assert orchestrator.advance()["status"] == "completed"
    parent_path = run_dir / "assets" / "fiber.png"
    original_bytes = parent_path.read_bytes()
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    execution = json.loads((run_dir / "plans" / "execution_result.json").read_text())
    validation = json.loads((run_dir / "validation" / "final.json").read_text())
    _mark_validation_failed(run_dir, validation, "multimodal_semantic")
    repair_plan = {
        "schema_version": "1.0",
        "artifact_type": "repair_plan",
        "run_id": client.state.run_id,
        "plan_ref": {"artifact": "plans/figure_plan.json",
                     "content_hash": hash_json(plan)},
        "execution_ref": {"artifact": "plans/execution_result.json",
                         "content_hash": hash_json(execution)},
        "validation_ref": {"artifact": "validation/final.json",
                          "content_hash": hash_json(validation)},
        "repairs": [{
            "asset_id": "fiber", "route": "image_edit",
            "operation": "raster_edit", "action": "make it blue",
            "source_check": "multimodal_semantic", "status": "pending",
        }],
        "status": "pending",
    }
    (run_dir / "plans" / "repair_plan.json").write_text(
        json.dumps(repair_plan), encoding="utf-8"
    )
    generation_before = client.state.calls_used("generation")

    result = orchestrator.advance({
        "action": "apply_repair",
        "repairs": [{
            "asset_id": "fiber",
            "operation": "raster_edit",
            "prompt": "make it blue",
        }],
    })

    assert result["status"] == "completed"
    assert client.state.calls_used("generation") == generation_before
    assert parent_path.read_bytes() == original_bytes
    outcome = json.loads(
        (run_dir / "validation" / "edit_outcomes" / "fiber.json").read_text()
    )
    assert outcome["status"] == "rolled_back"
    assert outcome["reason"] == "global validation regressed after raster edit"


def test_layout_patch_reuses_raster_asset_and_rebuilds_graph_layout(tmp_path: Path):
    orchestrator, run_dir, client = _orchestrator(tmp_path, _request())
    assert orchestrator.advance()["status"] == "completed"
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    execution = json.loads((run_dir / "plans" / "execution_result.json").read_text())
    validation = json.loads((run_dir / "validation" / "final.json").read_text())
    repair_plan = {
        "schema_version": "1.0",
        "artifact_type": "repair_plan",
        "run_id": client.state.run_id,
        "plan_ref": {"artifact": "plans/figure_plan.json",
                     "content_hash": hash_json(plan)},
        "execution_ref": {"artifact": "plans/execution_result.json",
                         "content_hash": hash_json(execution)},
        "validation_ref": {"artifact": "validation/final.json",
                          "content_hash": hash_json(validation)},
        "repairs": [{
            "asset_id": "fiber",
            "route": "image_edit",
            "operation": "layout_patch",
            "action": "move fiber inside panel b",
            "source_check": "layout",
            "status": "pending",
        }],
        "status": "pending",
    }
    (run_dir / "plans" / "repair_plan.json").write_text(
        json.dumps(repair_plan), encoding="utf-8"
    )
    generation_before = client.state.calls_used("generation")

    result = orchestrator.advance({
        "action": "apply_repair",
        "repairs": [{
            "asset_id": "fiber",
            "operation": "layout_patch",
            "bbox": [0.1, 0.1, 0.8, 0.8],
            "bbox_space": "panel",
        }],
    })

    assert result["status"] == "completed"
    assert client.state.calls_used("generation") == generation_before
    revised = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    fiber = next(item for item in revised["assets"] if item["asset_id"] == "fiber")
    assert revised["revision"] == 2
    assert fiber["bbox"] == [0.1, 0.1, 0.8, 0.8]
    assert fiber["bbox_space"] == "panel"
    solved_layout = json.loads((run_dir / "plans" / "solved_layout.json").read_text())
    node = next(
        item for item in solved_layout["nodes"] if item["node_id"] == "fiber"
    )
    assert node["bbox"] == [0.55, 0.1, 0.4, 0.8]


def test_connector_patch_rebuilds_port_bound_edge_without_regeneration(tmp_path: Path):
    request = _request()
    request["figure_graph"] = {
        "ports": [
            {"port_id": "curve-out", "node_id": "curve", "side": "right"},
            {"port_id": "fiber-in", "node_id": "fiber", "side": "left"},
            {"port_id": "fiber-out", "node_id": "fiber", "side": "right"},
            {"port_id": "curve-in", "node_id": "curve", "side": "left"},
        ],
        "typed_edges": [{
            "edge_id": "flow",
            "source_port": "curve-out",
            "target_port": "fiber-in",
            "direction": "forward",
            "semantic_type": "transfer",
        }],
        "groups": [],
        "labels": [],
        "constraints": [],
    }
    orchestrator, run_dir, client = _orchestrator(tmp_path, request)
    assert orchestrator.advance()["status"] == "completed"
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    execution = json.loads((run_dir / "plans" / "execution_result.json").read_text())
    validation = json.loads((run_dir / "validation" / "final.json").read_text())
    repair_plan = {
        "schema_version": "1.0",
        "artifact_type": "repair_plan",
        "run_id": client.state.run_id,
        "plan_ref": {"artifact": "plans/figure_plan.json",
                     "content_hash": hash_json(plan)},
        "execution_ref": {"artifact": "plans/execution_result.json",
                         "content_hash": hash_json(execution)},
        "validation_ref": {"artifact": "validation/final.json",
                          "content_hash": hash_json(validation)},
        "repairs": [{
            "asset_id": "fiber",
            "route": "image_edit",
            "operation": "connector_patch",
            "action": "reverse the flow",
            "source_check": "graph_edge_recovery",
            "status": "pending",
        }],
        "status": "pending",
    }
    (run_dir / "plans" / "repair_plan.json").write_text(
        json.dumps(repair_plan), encoding="utf-8"
    )
    generation_before = client.state.calls_used("generation")

    result = orchestrator.advance({
        "action": "apply_repair",
        "repairs": [{
            "asset_id": "fiber",
            "operation": "connector_patch",
            "edge_id": "flow",
            "source_port": "fiber-out",
            "target_port": "curve-in",
            "direction": "forward",
            "semantic_type": "feedback",
        }],
    })

    assert result["status"] == "completed"
    assert client.state.calls_used("generation") == generation_before
    graph = json.loads((run_dir / "plans" / "figure_graph.json").read_text())
    assert graph["typed_edges"] == [{
        "edge_id": "flow",
        "source_port": "fiber-out",
        "target_port": "curve-in",
        "direction": "forward",
        "semantic_type": "feedback",
    }]
    assembly_layout = json.loads(
        (run_dir / "assembly" / "layout_manifest.json").read_text()
    )
    connector = next(
        item for item in assembly_layout["elements"]
        if item["element_type"] == "connector"
    )
    assert connector["element_id"] == "edge:flow"
    assert connector["metadata"]["semantic_type"] == "feedback"


def test_force_export_publishes_existing_blocked_execution_without_regeneration(tmp_path: Path):
    request = _request()
    request["panels"][0]["elements"][0]["plot_spec"] = str(
        FIXTURES / "does_not_exist.json"
    )
    worker = RecordingWorker()
    orchestrator, run_dir, client = _orchestrator(tmp_path, request, worker)
    paused = orchestrator.advance()
    assert paused["next_action"] == "repair_required"
    calls_after_review = list(client.transport.calls)

    forced = orchestrator.advance({
        "action": "force_export",
        "reason": "Reviewed the missing optional comparison panel",
    })

    assert forced["status"] == "completed"
    assert (run_dir / "exports" / "figure.png").is_file()
    assert client.transport.calls == calls_after_review
    assert [inv.phase for inv in worker.invocations] == [
        "intake", "planning", "review_and_repair",
    ]
    report = (run_dir / "generation_report.md").read_text(encoding="utf-8")
    assert "Reviewed the missing optional comparison panel" in report
    state = json.loads((run_dir / "run_state.json").read_text())
    assert state["audit_log"][-1]["event"] == "force_export"


def test_incomplete_figure_brief_is_schema_valid_draft(tmp_path: Path):
    request = _request(export_target=None, figure_width_cm=None,
                       language=None, style=None)
    orchestrator, run_dir, _ = _orchestrator(tmp_path, request)

    orchestrator.advance()

    brief = json.loads((run_dir / "plans" / "figure_brief.json").read_text())
    schema = json.loads(schema_path("figure-brief.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(brief))
    assert brief["status"] == "draft"
    assert len(brief["required_clarifications"]) == 4


def test_approved_hybrid_run_returns_artifacts_through_one_seam(tmp_path: Path):
    worker = RecordingWorker()
    orchestrator, run_dir, _ = _orchestrator(tmp_path, _request(), worker)

    result = orchestrator.advance()

    assert result["phase"] == "export"
    assert result["status"] == "completed"
    assert result["next_action"] is None
    assert result["artifacts"]["figure_brief"]
    assert result["artifacts"]["figure_plan"]
    assert result["artifacts"]["execution_result"]
    assert result["artifacts"]["validation_report"]
    assert result["artifacts"]["exports"]
    assert (run_dir / "exports" / "figure.png").is_file()
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    assert plan["brief_ref"]["artifact"] == "plans/figure_brief.json"
    assert plan["delivery"]["export_target"] == "general"
    assert plan["language"] == "en"
    assert plan["style"] == "default"
    assert [inv.phase for inv in worker.invocations] == [
        "intake", "planning", "review_and_repair",
    ]


def test_plan_approval_is_explicit_and_does_not_generate_before_approval(tmp_path: Path):
    request = _request(auto_execute=False)
    orchestrator, run_dir, client = _orchestrator(tmp_path, request)

    paused = orchestrator.advance()

    assert paused["phase"] == "planning"
    assert paused["status"] == "paused"
    assert paused["next_action"] == "approve_plan"
    assert (run_dir / "plans" / "figure_plan.json").is_file()
    assert not client.transport.calls

    completed = orchestrator.advance("approve_plan")

    assert completed["status"] == "completed"
    assert (run_dir / "exports" / "figure.svg").is_file()


def test_execution_uses_the_approved_plan_not_mutated_raw_request(tmp_path: Path):
    request = _request(auto_execute=False)
    orchestrator, run_dir, _ = _orchestrator(tmp_path, request)
    paused = orchestrator.advance()
    assert paused["next_action"] == "approve_plan"
    request["panels"][0]["elements"][0]["plot_spec"] = str(
        FIXTURES / "does_not_exist.json"
    )
    request["panels"][1]["elements"][0]["prompt"] = "mutated after approval"

    completed = orchestrator.advance("approve_plan")

    assert completed["status"] == "completed"
    assert (run_dir / "plots" / "curve" / "plot.png").is_file()
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    curve = next(asset for asset in plan["assets"] if asset["asset_id"] == "curve")
    fiber = next(asset for asset in plan["assets"] if asset["asset_id"] == "fiber")
    assert curve["source"]["plot_spec"].endswith("plot_spec_line.json")
    assert fiber["source"]["prompt"] == "optical fiber cross-section"


def test_worker_contexts_are_phase_scoped(tmp_path: Path):
    worker = RecordingWorker()
    orchestrator, _, _ = _orchestrator(tmp_path, _request(), worker)

    orchestrator.advance()

    by_phase = {inv.phase: inv for inv in worker.invocations}
    assert set(by_phase["intake"].context) == {"user_request", "run_id", "prompt_hash"}
    assert set(by_phase["planning"].context) == {
        "figure_brief", "default_canvas", "revision",
    }
    assert set(by_phase["review_and_repair"].context) == {
        "figure_brief", "figure_plan", "execution_result", "validation_reports", "run_id",
    }
    assert by_phase["planning"].context["figure_brief"]["schema_version"] == "1.0"
    for phase in ("intake", "planning", "review_and_repair"):
        prompt_text = (Path(orchestrator.run_dir) / "prompts" / f"{phase}.txt").read_text()
        metadata = json.loads(
            (Path(orchestrator.run_dir) / "prompts" / f"{phase}.json").read_text()
        )
        assert prompt_text
        assert metadata["prompt_version"] == "1.0"
        assert metadata["prompt_hash"].startswith("sha256:")


@pytest.mark.parametrize("action", ["unknown", {"action": "unknown"}])
def test_unknown_transition_is_rejected(tmp_path: Path, action):
    orchestrator, _, _ = _orchestrator(tmp_path, _request())
    with pytest.raises(ValueError, match="unknown orchestrator action"):
        orchestrator.advance(action)
