from __future__ import annotations

import json
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from figure_tools.execution import FigureExecution
from figure_tools.planning.artifacts import FigurePlanningArtifacts
from figure_tools.planning.planner import create_figure_plan
from figure_tools.providers.client import ProviderClient
from figure_tools.providers.transport import MockProviderTransport
from figure_tools.state import Cache, RunDirectory, RunState


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


class _CandidateTransport(MockProviderTransport):
    def __init__(self) -> None:
        super().__init__()
        self.generated = 0

    def _response(self, role, model, payload):
        if role == "generation":
            self.generated += 1
            image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
            if self.generated > 1:
                ImageDraw.Draw(image).ellipse(
                    (384, 384, 640, 640), fill=(40, 120, 200, 255)
                )
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return {"image_bytes": buffer.getvalue(), "model": model, "seed": 0}
        return super()._response(role, model, payload)


def _request():
    return {
        "figure_id": "execution-figure",
        "run_id": "execution-run",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": [
            {
                "panel_id": "a",
                "bbox": [0, 0, 1, 1],
                "physical_size": [180, 112.5],
                "elements": [{
                    "element_id": "curve",
                    "type": "data_plot",
                    "plot_spec": str(FIXTURES / "plot_spec_line.json"),
                }],
            }
        ],
        "labels": [{"element_id": "label-a", "kind": "label", "content": "(a)"}],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "auto_execute": True,
    }


def test_execution_accepts_an_approved_plan_without_owning_lifecycle_decisions(tmp_path):
    run_dir = RunDirectory(tmp_path).create("execution-figure")
    state = RunState("execution-run", budget={})
    client = ProviderClient(
        {
            "image_generate": {"model": "mock"},
            "vision_validate": {"model": "mock"},
        },
        MockProviderTransport(),
        state=state,
        cache=Cache(tmp_path / "cache"),
        output_dir=run_dir,
    )
    request = _request()
    plan = create_figure_plan(request)
    execution_module = FigureExecution(
        request,
        config={},
        run_dir=run_dir,
        provider_client=client,
        state=state,
        base_dir=ROOT,
    )

    assert not hasattr(execution_module, "run")
    assert not hasattr(execution_module, "prepare_plan_artifacts")
    layout = FigurePlanningArtifacts(
        request, {}, run_dir, client, base_dir=ROOT,
    ).prepare(plan)
    result = execution_module.execute_plan(plan, layout_report=layout)
    published = execution_module.publish(
        {"plan": plan, "export_target": "general"}, result
    )

    assert result["paused"] is False
    assert (run_dir / "plans" / "figure_graph.json").is_file()
    assert (run_dir / "plans" / "solved_layout.json").is_file()
    assert (run_dir / "plans" / "figure_blueprint.svg").is_file()
    structure_questions = json.loads(
        (run_dir / "plans" / "structure_questions.json").read_text()
    )
    assert {item["level"] for item in structure_questions["questions"]} == {
        "component", "local_topology", "phase", "global_semantics",
    }
    persisted_plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    assert persisted_plan["figure_graph_ref"]["content_hash"].startswith("sha256:")
    assert persisted_plan["solved_layout_ref"]["content_hash"].startswith("sha256:")
    final_report = json.loads((run_dir / "validation" / "final.json").read_text())
    final_checks = {item["check_id"]: item for item in final_report["checks"]}
    assert final_checks["graph_node_recovery"]["status"] == "pass"
    assert final_checks["graph_edge_recovery"]["status"] == "pass"
    final_request = next(
        item for item in client.transport.requests
        if item["role"] == "final_validation"
    )
    assert "Are all required components present?" in final_request["payload"][
        "checks"
    ]
    assert (run_dir / "plots" / "curve" / "plot.png").is_file()
    assert (run_dir / "assembly" / "figure.png").is_file()
    assert (run_dir / "validation" / "final.json").is_file()
    assert published["exported"] is True


def test_execution_compiles_generation_conditions_and_uses_asset_placements(tmp_path):
    run_dir = RunDirectory(tmp_path).create("mechanism-figure")
    state = RunState("mechanism-run", budget={})
    transport = MockProviderTransport()
    client = ProviderClient(
        {
            "image_generate": {"model": "mock", "provider": "images"},
            "vision_validate": {"model": "mock", "provider": "vision"},
        },
        transport,
        state=state,
        cache=Cache(tmp_path / "cache"),
        output_dir=run_dir,
    )
    request = {
        "figure_id": "mechanism-figure",
        "run_id": "mechanism-run",
        "canvas": {"aspect_ratio": 2.0, "width": 180, "height": 90},
        "units": "mm",
        "panels": [{
            "panel_id": "a",
            "bbox": [0.2, 0.1, 0.6, 0.8],
            "physical_size": [108, 72],
            "elements": [
                {
                    "element_id": "receptor",
                    "type": "image_asset",
                    "prompt": "isolated receptor",
                    "bbox": [0.0, 0.0, 0.4, 1.0],
                },
                {
                    "element_id": "cell",
                    "type": "image_asset",
                    "prompt": "isolated cell",
                    "bbox": [0.6, 0.0, 0.4, 1.0],
                },
            ],
        }],
        "labels": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "publication_profile": "nature_research",
        "auto_execute": True,
    }
    config = {
        "models": {
            "image_generate": {"model": "mock", "provider": "images"},
        },
        "providers": {
            "images": {"type": "openai", "supports_reference_image": True},
        },
    }
    plan = create_figure_plan(request)
    module = FigureExecution(
        request, config, run_dir, client, state, base_dir=ROOT,
    )

    layout = FigurePlanningArtifacts(
        request, config, run_dir, client, base_dir=ROOT,
    ).prepare(plan)
    conditions = json.loads(
        (run_dir / "plans" / "generation_conditions.json").read_text()
    )
    paused = module.execute_plan(plan, layout_report=layout)
    pre_rendered = json.loads(
        (run_dir / "plans" / "pre_rendered_assets.json").read_text()
    )
    result = module.execute_plan(
        plan,
        layout_report=layout,
        style_anchor_approved=True,
        pre_rendered_assets=pre_rendered,
    )

    by_id = {item["asset_id"]: item for item in conditions["conditions"]}
    assert paused["pause_reason"] == "style_anchor_approval"
    assert by_id["receptor"]["publication_profile"]["profile_id"] == (
        "nature_research"
    )
    assert "isometric" in by_id["receptor"]["prompt"]
    manifest_by_id = {
        item["asset_id"]: item for item in result["manifest"]["assets"]
    }
    assert manifest_by_id["receptor"]["condition_hash"] == by_id["receptor"][
        "condition_hash"
    ]
    assert {item["asset_id"]: item["bbox"] for item in result["placements"]} == {
        "receptor": [0.2, 0.1, 0.24, 0.8],
        "cell": [0.56, 0.1, 0.24, 0.8],
    }


def test_approved_style_anchor_conditions_later_assets(tmp_path):
    run_dir = RunDirectory(tmp_path).create("style-anchor")
    state = RunState("style-anchor-run", budget={})
    transport = MockProviderTransport()
    client = ProviderClient(
        {
            "image_generate": {"model": "mock", "provider": "images"},
            "vision_validate": {"model": "mock", "provider": "vision"},
        },
        transport,
        state=state,
        cache=Cache(tmp_path / "cache"),
        output_dir=run_dir,
    )
    request = {
        "figure_id": "style-anchor",
        "run_id": "style-anchor-run",
        "canvas": {"aspect_ratio": 2.0, "width": 180, "height": 90},
        "units": "mm",
        "panels": [
            {
                "panel_id": f"panel-{index}",
                "bbox": [index / 4, 0, 1 / 4, 1],
                "physical_size": [45, 90],
                "elements": [{
                    "element_id": f"asset-{index}",
                    "type": "image_asset",
                    "prompt": f"isolated asset {index}",
                    "style_group": f"group-{index // 2}",
                }],
            }
            for index in range(4)
        ],
        "labels": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "auto_execute": True,
    }
    config = {
        "models": {
            "image_generate": {"model": "mock", "provider": "images"},
        },
        "providers": {
            "images": {"type": "openai", "supports_reference_image": True},
        },
    }
    plan = create_figure_plan(request)
    module = FigureExecution(request, config, run_dir, client, state, base_dir=ROOT)
    layout = FigurePlanningArtifacts(
        request, config, run_dir, client, base_dir=ROOT,
    ).prepare(plan)
    approved_conditions = (
        run_dir / "plans" / "generation_conditions.json"
    ).read_bytes()

    paused = module.execute_plan(plan, layout_report=layout)
    pre_rendered = json.loads(
        (run_dir / "plans" / "pre_rendered_assets.json").read_text()
    )
    completed = module.execute_plan(
        plan,
        layout_report=layout,
        style_anchor_approved=True,
        pre_rendered_assets=pre_rendered,
    )

    generation_requests = [
        item for item in transport.requests if item["role"] == "generation"
    ]
    assert paused["pause_reason"] == "style_anchor_approval"
    assert completed["paused"] is False
    assert (
        run_dir / "plans" / "generation_conditions.json"
    ).read_bytes() == approved_conditions
    assert (run_dir / "assets" / "style_anchor_conditions.json").is_file()
    assert len(generation_requests) == 4
    assert generation_requests[0]["image_paths"] == []
    assert generation_requests[1]["image_paths"] == []
    later_requests = generation_requests[2:]
    assert all(item["payload"]["references"] == [
        {"role": "style", "strength": 1.0}
    ] for item in later_requests)
    assert {item["image_paths"][0] for item in later_requests} == {
        pre_rendered["asset-0"]["path"],
        pre_rendered["asset-2"]["path"],
    }


def test_candidate_selection_rejects_a_blocking_candidate(tmp_path):
    run_dir = RunDirectory(tmp_path).create("candidate-selection")
    state = RunState("candidate-run", budget={})
    transport = _CandidateTransport()
    client = ProviderClient(
        {
            "image_generate": {"model": "mock"},
            "vision_validate": {"model": "mock"},
        },
        transport,
        state=state,
        cache=Cache(tmp_path / "cache"),
        output_dir=run_dir,
    )
    request = {
        "figure_id": "candidate-selection",
        "run_id": "candidate-run",
        "canvas": {"aspect_ratio": 2.0, "width": 180, "height": 90},
        "units": "mm",
        "panels": [{
            "panel_id": "a",
            "bbox": [0, 0, 1, 1],
            "physical_size": [80, 80],
            "elements": [{
                "element_id": "cell",
                "type": "image_asset",
                "prompt": "isolated cell",
                "candidate_count": 2,
            }],
        }],
        "labels": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "auto_execute": True,
    }
    plan = create_figure_plan(request)
    module = FigureExecution(request, {}, run_dir, client, state, base_dir=ROOT)
    layout = FigurePlanningArtifacts(
        request, {}, run_dir, client, base_dir=ROOT,
    ).prepare(plan)

    result = module.execute_plan(plan, layout_report=layout)
    selection = json.loads(
        (run_dir / "validation" / "candidate_selection" / "cell.json").read_text()
    )

    assert result["paused"] is False
    assert transport.generated == 2
    assert selection["selected_candidate"] == 2
    assert selection["candidates"][0]["blocking"] is True
    assert selection["candidates"][1]["blocking"] is False


def test_planning_rejects_stale_reference_hash_before_provider_work(tmp_path):
    reference = tmp_path / "style.png"
    Image.new("RGB", (8, 8), "white").save(reference)
    run_dir = RunDirectory(tmp_path).create("stale-reference")
    state = RunState("stale-reference", budget={})
    transport = MockProviderTransport()
    client = ProviderClient(
        {"image_generate": {"model": "mock"}},
        transport,
        state=state,
        cache=Cache(tmp_path / "cache"),
        output_dir=run_dir,
    )
    request = {
        "figure_id": "stale-reference",
        "canvas": {"aspect_ratio": 2.0, "width": 180, "height": 90},
        "units": "mm",
        "panels": [{
            "panel_id": "a",
            "bbox": [0, 0, 1, 1],
            "physical_size": [89, 80],
            "elements": [{
                "element_id": "cell",
                "type": "image_asset",
                "prompt": "cell",
                "references": [{
                    "role": "style",
                    "path": str(reference),
                    "content_hash": "sha256:stale",
                    "strength": 0.75,
                }],
            }],
        }],
        "labels": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "style": "default",
    }
    plan = create_figure_plan(request)
    planning = FigurePlanningArtifacts(
        request,
        {
            "models": {"image_generate": {"model": "mock", "provider": "images"}},
            "providers": {
                "images": {"type": "openai", "supports_reference_image": True},
            },
        },
        run_dir,
        client,
        base_dir=ROOT,
    )

    with pytest.raises(ValueError, match="reference hash mismatch"):
        planning.prepare(plan)

    assert transport.requests == []
