"""Task router and figure-plan builder tests (plan sections 2, 7, 15)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.planning.planner import (
    collect_required_clarifications,
    create_figure_plan,
)
from figure_tools.planning.router import classify_task, route_element

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


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
                           "prompt": "optical fiber"}]},
        ],
        "labels": [{"element_id": "label-a", "kind": "label", "content": "(a)"}],
        "assumptions": ["Gaussian beam approximation."],
        "uncertainties": [],
        "user_input_requirements": [],
    }
    base.update(over)
    return base


def test_classify_hybrid():
    assert classify_task(_request()) == "hybrid"


def test_classify_data_plot_only():
    req = _request()
    req["panels"][1]["elements"] = []
    assert classify_task(req) == "data_plot"


def test_classify_schematic_only():
    req = _request()
    req["panels"][0]["elements"] = []
    assert classify_task(req) == "schematic"


def test_route_element():
    assert route_element({"type": "data_plot"}) == "python"
    assert route_element({"type": "image_asset"}) == "image_model"
    assert route_element({"type": "label"}) == "svg"
    assert route_element({"type": "equation"}) == "svg"


def test_create_figure_plan_conforms_to_schema():
    plan = create_figure_plan(_request())
    schema = json.loads(schema_path("figure-plan.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(plan))


def test_plan_routes_data_plot_to_python_and_ai_to_image_model():
    plan = create_figure_plan(_request())
    by_id = {a["asset_id"]: a for a in plan["assets"]}
    assert by_id["curve"]["routing"] == "python"
    assert by_id["curve"]["type"] == "data_plot"
    assert by_id["fiber"]["routing"] == "image_model"
    assert by_id["fiber"]["type"] == "image_asset"
    assert by_id["label-a"]["routing"] == "svg"


def test_plan_records_panel_relative_asset_bbox_when_element_declares_one():
    request = _request()
    request["panels"][1]["elements"][0]["bbox"] = [0.1, 0.2, 0.7, 0.6]

    plan = create_figure_plan(request)
    asset = next(item for item in plan["assets"] if item["asset_id"] == "fiber")

    assert asset["bbox"] == [0.1, 0.2, 0.7, 0.6]
    assert asset["bbox_space"] == "panel"


def test_plan_estimates_paid_calls():
    plan = create_figure_plan(_request())
    est = plan["estimated_paid_calls"]
    assert est["generation"] == 1  # one AI asset
    assert est["validations"] == 1  # one per AI asset
    assert est["final_validation"] == 1


def test_plan_estimates_disclosed_candidate_calls():
    request = _request()
    request["panels"][1]["elements"][0]["candidate_count"] = 3

    estimated = create_figure_plan(request)["estimated_paid_calls"]

    assert estimated["generation"] == 3
    assert estimated["validations"] == 3


def test_plan_discloses_every_per_asset_reference_upload():
    request = _request()
    request["panels"][1]["elements"][0]["references"] = [{
        "role": "style",
        "path": "/references/style.png",
        "content_hash": "sha256:style",
        "strength": 0.75,
    }]

    uploads = create_figure_plan(request)["planned_uploads"]

    assert {item["path"] for item in uploads} == {"/references/style.png"}
    assert uploads[0]["reason"] == "style reference for fiber"


def test_plan_approval_pending_by_default():
    plan = create_figure_plan(_request())
    assert plan["approval"]["status"] == "pending"


def test_plan_records_user_input_requirements():
    req = _request(user_input_requirements=["Confirm wavelength 1550 nm."])
    plan = create_figure_plan(req)
    assert plan["user_input_requirements"][0] == "Confirm wavelength 1550 nm."
    assert any("output target" in item for item in plan["user_input_requirements"])


def test_plan_asks_for_output_target_when_missing():
    plan = create_figure_plan(_request())
    assert any("output target" in item for item in plan["user_input_requirements"])


def test_plan_skips_output_target_question_when_provided():
    plan = create_figure_plan(_request(export_target="ppt"))
    assert not any("output target" in item for item in plan["user_input_requirements"])


def test_plan_asks_for_figure_width_when_missing():
    plan = create_figure_plan(_request())
    assert any("figure width" in item for item in plan["user_input_requirements"])
    assert any("6.5" in item and "14" in item for item in plan["user_input_requirements"])


def test_plan_skips_figure_width_question_when_provided():
    plan = create_figure_plan(_request(figure_width_cm=6.5))
    assert not any("figure width" in item for item in plan["user_input_requirements"])


def test_plan_asks_for_language_when_missing():
    plan = create_figure_plan(_request())
    assert any("language" in item for item in plan["user_input_requirements"])


def test_plan_asks_for_style_when_missing():
    plan = create_figure_plan(_request())
    assert any("style" in item for item in plan["user_input_requirements"])


def test_plan_skips_language_and_style_questions_when_provided():
    plan = create_figure_plan(_request(language="en", style="default"))
    assert not any("language" in item for item in plan["user_input_requirements"])
    assert not any("style" in item for item in plan["user_input_requirements"])


def test_collect_required_clarifications_returns_all_unresolved():
    clarifications = collect_required_clarifications(_request())
    fields = {c["field"] for c in clarifications}
    assert {"export_target", "figure_width_cm", "language", "style"} <= fields


def test_collect_required_clarifications_empty_when_resolved():
    clarifications = collect_required_clarifications(
        _request(export_target="general", figure_width_cm=14.0,
                 language="en", style="default")
    )
    assert clarifications == []


def test_clarification_questions_match_between_output_paths():
    """create_figure_plan and collect_required_clarifications must derive the
    same questions from REQUIRED_CLARIFICATIONS — no drift between the two
    output shapes."""
    req = _request()
    plan = create_figure_plan(req)
    from_plan = {q for q in plan["user_input_requirements"]
                 if q.startswith("Confirm")}
    from_collect = {c["question"]
                    for c in collect_required_clarifications(req)}
    assert from_plan == from_collect
    assert len(from_plan) == 4


def test_figure_width_overrides_canvas_dimensions():
    plan = create_figure_plan(_request(figure_width_cm=6.5))
    assert plan["canvas"]["width"] == 65.0
    assert plan["canvas"]["height"] == 32.5
    assert plan["canvas"]["aspect_ratio"] == 2.0


def test_plan_style_bible_ref_defaults():
    plan = create_figure_plan(_request())
    assert plan["style_bible_ref"] == "default"


def test_plan_carries_delivery_language_and_style_constraints():
    plan = create_figure_plan(
        _request(export_target="ppt", figure_width_cm=6.5,
                 language="en", style="custom-style"),
        style_bible_ref="custom-style",
    )
    assert plan["delivery"] == {"export_target": "ppt", "figure_width_cm": 6.5}
    assert plan["language"] == "en"
    assert plan["style"] == "custom-style"
    assert plan["style_bible_ref"] == "custom-style"
