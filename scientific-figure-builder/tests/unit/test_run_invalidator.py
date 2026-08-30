from __future__ import annotations

import copy
from pathlib import Path

import pytest

from figure_tools.run_invalidator import RunInvalidator
from figure_tools.state import RunState


ARTIFACTS = (
    "plans/figure_brief.json",
    "plans/figure_plan.json",
    "plans/layout_wireframe.svg",
    "plans/layout_analysis.json",
    "plans/figure_graph.json",
    "plans/solved_layout.json",
    "plans/figure_blueprint.svg",
    "plans/structure_questions.json",
    "plans/generation_conditions.json",
    "plans/execution_result.json",
    "plans/repair_plan.json",
    "plans/export_result.json",
    "asset_manifest.json",
    "generation_report.md",
    "plots/plot-a/plot.png",
    "plots/plot-b/plot.png",
    "vectors/label-a.svg",
    "assets/raster-a.png",
    "assembly/figure.png",
    "validation/final.json",
    "exports/figure.png",
)


def _prepared_run(tmp_path: Path) -> tuple[RunInvalidator, RunState]:
    for relative in ARTIFACTS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    state = RunState("run-1")
    for step in ("planning", "planning_approval", "execution", "review_and_repair", "export"):
        state.mark_step(step, "completed")
    for name in ("figure_plan", "execution_result", "validation_report", "export_result", "exports"):
        state.set_artifact(name, {"path": name})
    return RunInvalidator(tmp_path, state), state


def test_figure_brief_change_invalidates_every_dependent_artifact(tmp_path):
    invalidator, state = _prepared_run(tmp_path)

    plan = invalidator.after_figure_brief_change()

    assert (tmp_path / "plans/figure_brief.json").exists()
    assert not (tmp_path / "plans/figure_plan.json").exists()
    assert not (tmp_path / "assets/raster-a.png").exists()
    assert state.step_status("planning") == "pending"
    assert state.artifact("figure_plan") is None
    assert "plans/figure_plan.json" in plan.removed_paths


def test_clarification_submission_replaces_the_draft_brief_and_request(tmp_path):
    invalidator, state = _prepared_run(tmp_path)
    request_path = tmp_path / "plans" / "request.json"
    request_path.write_text("request", encoding="utf-8")

    invalidator.for_clarification_submission()

    assert not (tmp_path / "plans" / "figure_brief.json").exists()
    assert not request_path.exists()
    assert state.step_status("intake") == "pending"


def test_figure_plan_change_preserves_the_new_plan_and_invalidates_derived_outputs(tmp_path):
    invalidator, state = _prepared_run(tmp_path)
    previous = {
        "panels": [{"panel_id": "a", "bbox": [0, 0, 1, 1]}],
        "assets": [
            {"asset_id": "plot-a", "type": "data_plot", "source": {"plot_spec": "a"}},
            {"asset_id": "label-a", "type": "text", "source": {"content": "A"}},
            {"asset_id": "raster-a", "type": "image_asset", "source": {"prompt": "A"}},
        ],
        "delivery": {"export_target": "general"},
    }
    current = copy.deepcopy(previous)
    current["panels"][0]["bbox"] = [0.1, 0, 0.9, 1]

    invalidator.after_figure_plan_change(previous, current)

    assert (tmp_path / "plans/figure_plan.json").exists()
    assert not (tmp_path / "plans/layout_analysis.json").exists()
    assert not (tmp_path / "plans/figure_graph.json").exists()
    assert not (tmp_path / "plans/generation_conditions.json").exists()
    assert (tmp_path / "plots/plot-a/plot.png").exists()
    assert (tmp_path / "vectors/label-a.svg").exists()
    assert (tmp_path / "assets/raster-a.png").exists()
    assert not (tmp_path / "assembly/figure.png").exists()
    assert state.step_status("planning") == "completed"
    assert state.step_status("planning_approval") == "pending"
    assert state.step_status("execution") == "pending"


def test_figure_plan_source_change_invalidates_only_the_changed_asset(tmp_path):
    invalidator, _state = _prepared_run(tmp_path)
    previous = {"assets": [
        {"asset_id": "plot-a", "type": "data_plot", "source": {"plot_spec": "old"}},
        {"asset_id": "raster-a", "type": "image_asset", "source": {"prompt": "same"}},
    ]}
    current = copy.deepcopy(previous)
    current["assets"][0]["source"]["plot_spec"] = "new"

    invalidator.after_figure_plan_change(previous, current)

    assert not (tmp_path / "plots/plot-a/plot.png").exists()
    assert (tmp_path / "plots/plot-b/plot.png").exists()
    assert (tmp_path / "assets/raster-a.png").exists()


@pytest.mark.parametrize(
    ("route", "asset_id", "removed", "retained"),
    [
        ("python", "plot-a", "plots/plot-a/plot.png", "plots/plot-b/plot.png"),
        ("svg", "label-a", "vectors/label-a.svg", "plots/plot-a/plot.png"),
        ("image_edit", "raster-a", "assembly/figure.png", "assets/raster-a.png"),
    ],
)
def test_repair_invalidation_is_route_specific(
    tmp_path, route, asset_id, removed, retained
):
    invalidator, state = _prepared_run(tmp_path)

    invalidator.after_repairs({asset_id: route})

    assert not (tmp_path / removed).exists()
    assert (tmp_path / retained).exists()
    assert not (tmp_path / "validation/final.json").exists()
    assert not (tmp_path / "exports/figure.png").exists()
    assert state.step_status("execution") == "pending"


def test_assembly_change_and_export_rerun_have_narrow_downstream_plans(tmp_path):
    invalidator, _state = _prepared_run(tmp_path)

    invalidator.after_assembly_change()

    assert (tmp_path / "assembly/figure.png").exists()
    assert (tmp_path / "assets/raster-a.png").exists()
    assert not (tmp_path / "validation/final.json").exists()
    assert not (tmp_path / "exports/figure.png").exists()

    (tmp_path / "validation/final.json").parent.mkdir(exist_ok=True)
    (tmp_path / "validation/final.json").write_text("valid", encoding="utf-8")
    (tmp_path / "exports/figure.png").parent.mkdir(exist_ok=True)
    (tmp_path / "exports/figure.png").write_text("export", encoding="utf-8")
    invalidator.for_export_rerun()

    assert (tmp_path / "validation/final.json").exists()
    assert not (tmp_path / "exports/figure.png").exists()
