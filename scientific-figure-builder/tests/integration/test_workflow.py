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
    # Ark is used only for isolated asset generation + validation.
    assert roles_used <= {"generation", "validations"}
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
