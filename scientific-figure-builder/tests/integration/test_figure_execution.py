from __future__ import annotations

from pathlib import Path

from figure_tools.execution import FigureExecution
from figure_tools.planning.planner import create_figure_plan
from figure_tools.providers.client import ProviderClient
from figure_tools.providers.transport import MockProviderTransport
from figure_tools.state import Cache, RunDirectory, RunState


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


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
    layout = execution_module.prepare_plan_artifacts(plan)
    result = execution_module.execute_plan(plan, layout_report=layout)
    published = execution_module.publish(
        {"plan": plan, "export_target": "general"}, result
    )

    assert result["paused"] is False
    assert (run_dir / "plots" / "curve" / "plot.png").is_file()
    assert (run_dir / "assembly" / "figure.png").is_file()
    assert (run_dir / "validation" / "final.json").is_file()
    assert published["exported"] is True
