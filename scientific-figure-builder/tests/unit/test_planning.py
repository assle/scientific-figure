"""Task router and figure-plan builder tests (plan sections 2, 7, 15)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.planning.planner import create_figure_plan
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
    assert route_element({"type": "image_asset"}) == "ark_image"
    assert route_element({"type": "label"}) == "svg"
    assert route_element({"type": "equation"}) == "svg"


def test_create_figure_plan_conforms_to_schema():
    plan = create_figure_plan(_request())
    schema = json.loads(schema_path("figure-plan.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(plan))


def test_plan_routes_data_plot_to_python_and_ai_to_ark():
    plan = create_figure_plan(_request())
    by_id = {a["asset_id"]: a for a in plan["assets"]}
    assert by_id["curve"]["routing"] == "python"
    assert by_id["curve"]["type"] == "data_plot"
    assert by_id["fiber"]["routing"] == "ark_image"
    assert by_id["fiber"]["type"] == "image_asset"
    assert by_id["label-a"]["routing"] == "svg"


def test_plan_estimates_paid_calls():
    plan = create_figure_plan(_request())
    est = plan["estimated_paid_calls"]
    assert est["generation"] == 1  # one AI asset
    assert est["validations"] == 1  # one per AI asset
    assert est["final_validation"] == 1


def test_plan_approval_pending_by_default():
    plan = create_figure_plan(_request())
    assert plan["approval"]["status"] == "pending"


def test_plan_records_user_input_requirements():
    req = _request(user_input_requirements=["Confirm wavelength 1550 nm."])
    plan = create_figure_plan(req)
    assert plan["user_input_requirements"] == ["Confirm wavelength 1550 nm."]


def test_plan_style_bible_ref_defaults():
    plan = create_figure_plan(_request())
    assert plan["style_bible_ref"] == "default"
