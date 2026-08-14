"""Full figure workflow tests (plan section 15, Phase 5 exit criteria).

- Formal outputs never contain image-model-generated text, axes, or data plots.
- Scientific ambiguity pauses for user input.
- Warnings and blocking errors behave as specified.

All runs use MockArkTransport - no paid calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from figure_tools.ark.client import ArkClient
from figure_tools.ark.transport import MockArkTransport
from figure_tools.state import Cache, RunDirectory, RunState
from figure_tools.workflow import FigureWorkflow

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"

MODELS = {
    "image_generate": {"model": "ep-gen"},
    "image_edit": {"model": "ep-edit"},
    "vision_analyze": {"model": "ep-analyze"},
    "vision_validate": {"model": "ep-validate"},
}
BUDGET = {"reference_analysis": 1, "generation": 5, "edits": 2,
          "validations": 5, "final_validation": 1}


def _request(auto_execute=True, **over):
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
        "auto_execute": auto_execute,
    }
    base.update(over)
    return base


def _workflow(tmp_path: Path, request, transport=None, compose_dpi=300):
    run_dir = RunDirectory(base_dir=tmp_path).create(request["figure_id"])
    transport = transport or MockArkTransport()
    state = RunState(run_id=run_dir.name, budget=BUDGET)
    cache = Cache(run_dir / "cache")
    client = ArkClient(MODELS, transport, api_key=None, state=state, cache=cache,
                       output_dir=run_dir)
    wf = FigureWorkflow(request, config={}, run_dir=run_dir, ark_client=client,
                        state=state, base_dir=ROOT, compose_dpi=compose_dpi)
    return wf, client, run_dir


def test_hybrid_run_produces_assembled_figure_and_report(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert result["paused"] is False
    assert (run_dir / "exports" / "figure.png").is_file()
    assert (run_dir / "exports" / "figure.svg").is_file()
    assert (run_dir / "exports" / "figure.pdf").is_file()
    assert (run_dir / "generation_report.md").is_file()
    assert (run_dir / "asset_manifest.json").is_file()
    assert (run_dir / "plans" / "figure_plan.json").is_file()
    assert (run_dir / "plans" / "layout_wireframe.svg").is_file()
    # Manifest conforms to the v1 schema.
    from jsonschema import Draft202012Validator
    from figure_tools._resources import schema_path
    manifest = json.loads((run_dir / "asset_manifest.json").read_text())
    schema = json.loads(schema_path("asset-manifest.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(manifest))


def test_image_model_never_generates_plots_axes_or_labels(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    roles_used = {role for role, _ in client.transport.calls}
    # Ark is used only for isolated asset generation + validation (per-asset and
    # final). It never generates plots, axes, or labels.
    assert roles_used <= {"generation", "validations", "final_validation"}
    # The data plot is a Python-rendered artifact, not an Ark output.
    assert (run_dir / "plots" / "curve" / "plot.png").is_file()
    # The AI asset is isolated and transparent.
    manifest = json.loads((run_dir / "asset_manifest.json").read_text())
    fiber = next(a for a in manifest["assets"] if a["asset_id"] == "fiber")
    assert fiber["transparent"] is True
    assert fiber["type"] == "image_asset"
    # Routing lives in the figure plan: data plot -> python, AI asset -> ark.
    plan_routing = {a["asset_id"]: a["routing"] for a in result["figure_plan"]["assets"]}
    assert plan_routing["curve"] == "python"
    assert plan_routing["fiber"] == "ark_image"


def test_scientific_ambiguity_pauses_before_generation(tmp_path: Path):
    req = _request(auto_execute=False,
                   user_input_requirements=["Confirm wavelength is 1550 nm."])
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run()
    assert result["paused"] is True
    # No paid generation happened.
    roles_used = {role for role, _ in client.transport.calls}
    assert "generation" not in roles_used
    assert not (run_dir / "exports" / "figure.png").exists()


def test_missing_required_clarifications_pause_before_generation(tmp_path: Path):
    req = _request(auto_execute=True, export_target=None, figure_width_cm=None,
                   language=None, style=None)
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run()
    assert result["paused"] is True
    assert result["pause_reason"] == "clarification_required"
    assert {c["field"] for c in result["clarifications"]} == {
        "export_target", "figure_width_cm", "language", "style",
    }
    roles_used = {role for role, _ in client.transport.calls}
    assert "generation" not in roles_used
    assert not (run_dir / "exports" / "figure.png").exists()


def test_blocking_error_prevents_export(tmp_path: Path):
    # A data_plot referencing a missing plot spec -> asset render fails ->
    # missing asset -> final validation blocks export.
    req = _request()
    req["panels"][0]["elements"][0]["plot_spec"] = str(FIXTURES / "does_not_exist.json")
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run()
    assert result["paused"] is False
    assert result["exported"] is False
    assert not (run_dir / "exports" / "figure.png").exists()
    assert any(r["summary"]["blocking"] for r in result["validation_reports"])


def test_warning_allows_export(tmp_path: Path):
    # Very low compose dpi -> effective_resolution warning, not blocking.
    wf, client, run_dir = _workflow(tmp_path, _request(), compose_dpi=24)
    result = wf.run()
    assert result["exported"] is True
    assert (run_dir / "exports" / "figure.png").is_file()
    final = result["validation_reports"][-1]
    assert final["summary"]["blocking"] is False
    assert final["summary"]["warnings"] >= 1


def test_style_anchor_pauses_when_three_or_more_ai_assets(tmp_path: Path):
    req = _request()
    # Add two more AI assets so total AI assets >= 3.
    req["panels"][1]["elements"].extend([
        {"element_id": "lens", "type": "image_asset", "prompt": "lens"},
        {"element_id": "detector", "type": "image_asset", "prompt": "detector"},
    ])
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run()
    assert result["paused"] is True
    assert result["pause_reason"] == "style_anchor_approval"
    # Only the single style-anchor asset was generated before pausing.
    gen_calls = sum(1 for role, _ in client.transport.calls if role == "generation")
    assert gen_calls == 1


def test_default_approval_flow_completes(tmp_path: Path):
    # Default (non auto_execute): plan approval pauses, then approved run proceeds.
    req = _request(auto_execute=False)
    wf, client, run_dir = _workflow(tmp_path, req)
    first = wf.run()
    assert first["paused"] is True
    assert first["pause_reason"] == "plan_approval"
    assert sum(1 for r, _ in client.transport.calls if r == "generation") == 0

    second = wf.run(approved=True)
    assert second["paused"] is False
    assert second["exported"] is True
    assert (run_dir / "exports" / "figure.png").is_file()


def test_style_anchor_resume_does_not_regenerate(tmp_path: Path):
    req = _request()
    req["panels"][1]["elements"].extend([
        {"element_id": "lens", "type": "image_asset", "prompt": "lens"},
        {"element_id": "detector", "type": "image_asset", "prompt": "detector"},
    ])
    wf, client, run_dir = _workflow(tmp_path, req)
    paused = wf.run()
    assert paused["pause_reason"] == "style_anchor_approval"
    calls_after_pause = len(client.transport.calls)

    resumed = wf.run(approved=True, style_anchor_approved=True)
    assert resumed["paused"] is False
    assert resumed["exported"] is True
    # Anchor was cached -> only the 2 remaining AI assets triggered new generation.
    new_gen = sum(1 for r, _ in client.transport.calls[calls_after_pause:] if r == "generation")
    assert new_gen == 2


# --- Spec 0001 quality improvements ---

def test_layout_analysis_generated_before_render(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert result["paused"] is False
    layout_path = run_dir / "plans" / "layout_analysis.json"
    assert layout_path.is_file()
    layout = json.loads(layout_path.read_text())
    assert layout["schema_version"] == "1.0"
    assert len(layout["panel_width_recommendations"]) == 2


def test_validation_reports_contain_layout_checks(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    all_check_ids = {c["check_id"] for r in result["validation_reports"]
                     for c in r.get("checks", [])}
    assert "legend_data_overlap" in all_check_ids
    assert "text_overlap" in all_check_ids
    assert "label_readability" in all_check_ids


def test_export_blocked_reason_when_validation_blocks(tmp_path: Path):
    req = _request()
    req["panels"][0]["elements"][0]["plot_spec"] = str(FIXTURES / "does_not_exist.json")
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run()
    assert result["exported"] is False
    assert result.get("export_blocked_reason") is not None


def test_root_cause_report_generated_on_validation_failure(tmp_path: Path):
    req = _request()
    req["panels"][0]["elements"][0]["plot_spec"] = str(FIXTURES / "does_not_exist.json")
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run()
    root_cause_path = run_dir / "validation" / "root_cause_report.json"
    assert root_cause_path.is_file()
    root_cause = json.loads(root_cause_path.read_text())
    assert root_cause["schema_version"] == "1.0"
    assert isinstance(root_cause["findings"], list)


def test_force_export_bypasses_gate(tmp_path: Path):
    req = _request()
    req["panels"][0]["elements"][0]["plot_spec"] = str(FIXTURES / "does_not_exist.json")
    wf, client, run_dir = _workflow(tmp_path, req)
    result = wf.run(force_export=True)
    assert result["exported"] is True
    assert (run_dir / "exports" / "figure.png").is_file()


def test_final_validation_report_written_to_disk(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert (run_dir / "validation" / "validation_report.json").is_file()
    report = json.loads((run_dir / "validation" / "validation_report.json").read_text())
    assert report["schema_version"] == "1.0"


def test_no_root_cause_report_when_all_pass(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request(), compose_dpi=600)
    result = wf.run()
    root_cause_path = run_dir / "validation" / "root_cause_report.json"
    assert not root_cause_path.exists()


# --- Image QA: final validation link fix (PR 1) ---

def test_final_validation_uses_ark_client_not_skipped(tmp_path: Path):
    """FigureWorkflow.run() must thread ark_client into final validation so the
    multimodal final check actually runs instead of defaulting to skipped."""
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert result["paused"] is False
    final = result["validation_reports"][-1]
    # The final_validation paid role was actually invoked, proving the ark
    # client was threaded into the final check (PR1 fix).
    assert any(role == "final_validation" for role, _ in client.transport.calls)
    # The model's multimodal checks are present in the final report.
    assert any(c["check_id"] == "multimodal_semantic" for c in final["checks"])


def test_final_validation_skipped_without_ark_client(tmp_path: Path):
    """Without an ark client the multimodal final check degrades to skipped.
    Verified at the unit level (the workflow needs ark for AI assets)."""
    from figure_tools.validation.engine import FigureQAEngine
    from figure_tools.validation.models import AssembledFigure
    composed = tmp_path / "figure.png"; _save_rgba_img(composed)
    curve = tmp_path / "curve.png"; _save_rgba_img(curve)
    fiber = tmp_path / "fiber.png"; _save_rgba_img(fiber)
    report = FigureQAEngine(config={}, ark_client=None).validate_final(
        AssembledFigure(
            figure_plan=_simple_plan(),
            asset_manifest=_simple_manifest(curve, fiber),
            image_path=composed,
            layout_manifest_path=None,
            physical_size_mm=(180, 112.5),
        ))
    mm = next(c for c in report["checks"] if c["check_id"] == "multimodal_final")
    assert mm["status"] == "skipped"
    assert report["summary"]["blocking"] is False


def _save_rgba_img(path: Path, size=(2048, 1280)):
    from PIL import Image, ImageDraw
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((400, 400, 1600, 880), fill=(200, 40, 40, 255))
    img.save(path)


def _simple_plan():
    return {
        "schema_version": "1.0", "figure_id": "f1", "run_id": "f1",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": [{"panel_id": "a", "bbox": [0, 0, 0.5, 1], "physical_size": [90, 112.5]},
                   {"panel_id": "b", "bbox": [0.5, 0, 0.5, 1], "physical_size": [90, 112.5]}],
        "assets": [{"asset_id": "curve", "type": "data_plot", "z_order": 1,
                    "dependencies": [], "routing": "python"},
                   {"asset_id": "fiber", "type": "image_asset", "z_order": 2,
                    "dependencies": [], "routing": "ark_image"}],
        "style_bible_ref": "default", "text_elements": [],
        "assumptions": [], "uncertainties": [], "user_input_requirements": [],
        "estimated_paid_calls": {}, "planned_uploads": [],
        "approval": {"status": "approved"},
    }


def _simple_manifest(curve_path, fiber_path, fiber_transparent=True):
    return {
        "schema_version": "1.0",
        "assets": [
            {"asset_id": "curve", "type": "data_plot", "path": str(curve_path),
             "content_hash": "sha256:c", "pixel_dimensions": [1024, 800],
             "transparent": False, "z_order": 1,
             "validation_result": {"status": "pass"}},
            {"asset_id": "fiber", "type": "image_asset", "path": str(fiber_path),
             "content_hash": "sha256:f", "pixel_dimensions": [2048, 1280],
             "transparent": fiber_transparent, "z_order": 2,
             "validation_result": {"status": "pass"}},
        ],
    }


def test_compose_return_value_used_for_composed_png(tmp_path: Path):
    """The workflow must consume compose_assets() return value rather than
    assuming a fixed filename (plan section 17.2)."""
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert (run_dir / "assembly" / "figure.png").is_file()
    assert result["exported"] is True


# --- Export target (issue #3) ---

def test_export_target_general_is_backward_compatible(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert result["exported"] is True
    plot_svg = (run_dir / "plots" / "curve" / "plot.svg").read_text(encoding="utf-8")
    figure_svg = (run_dir / "assembly" / "figure.svg").read_text(encoding="utf-8")
    assert "<use" in plot_svg
    assert "<text" not in plot_svg
    assert "<use" in figure_svg
    assert "<text" not in figure_svg


def test_export_target_ppt_flows_to_plot_and_figure(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request(export_target="ppt"))
    result = wf.run()
    assert result["exported"] is True
    plot_svg = (run_dir / "plots" / "curve" / "plot.svg").read_text(encoding="utf-8")
    figure_svg = (run_dir / "exports" / "figure.svg").read_text(encoding="utf-8")
    assert "<text" in plot_svg
    assert "text-anchor" in plot_svg
    assert "<text" in figure_svg
    # PNG/PDF remain available and non-empty.
    assert (run_dir / "exports" / "figure.png").stat().st_size > 0
    assert (run_dir / "exports" / "figure.pdf").stat().st_size > 0


def test_export_target_recorded_in_generation_report(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request(export_target="ppt"))
    wf.run()
    report = (run_dir / "generation_report.md").read_text(encoding="utf-8")
    assert "Export target: ppt" in report


# --- Image QA: local VLM review (PR 6) ---

def test_no_local_vlm_calls_when_no_layout_issues(tmp_path: Path):
    """A clean figure produces no local-region VLM calls (plan section 20.3)."""
    wf, client, run_dir = _workflow(tmp_path, _request(), compose_dpi=600)
    result = wf.run()
    assert result["exported"] is True
    assert client.transport.local_region_calls == 0
    # The whole-image final validation still ran.
    assert any(role == "final_validation" for role, _ in client.transport.calls)


def test_final_report_written_to_validation_final_json(tmp_path: Path):
    wf, client, run_dir = _workflow(tmp_path, _request())
    result = wf.run()
    assert (run_dir / "validation" / "final.json").is_file()
    final = json.loads((run_dir / "validation" / "final.json").read_text())
    assert final["schema_version"] == "1.0"
