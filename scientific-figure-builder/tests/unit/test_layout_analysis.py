"""Pre-render layout analysis tests (spec 0001, improvement 2).

Pure-function tests for analyze_layout: panel width recommendations,
legend placement recommendations, and warnings.
"""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.planning.layout_analysis import analyze_layout


def _figure_plan(panels=None):
    return {
        "schema_version": "1.0",
        "figure_id": "f1",
        "run_id": "f1",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": panels or [
            {"panel_id": "a", "bbox": [0, 0, 0.5, 1], "physical_size": [90, 112.5]},
            {"panel_id": "b", "bbox": [0.5, 0, 0.5, 1], "physical_size": [90, 112.5]},
        ],
        "assets": [],
        "style_bible_ref": "default",
        "text_elements": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "estimated_paid_calls": {},
        "planned_uploads": [],
        "approval": {"status": "approved"},
    }


def _data_characteristics(panels=None):
    return {"panels": panels or {
        "a": {
            "data_element_count": 3,
            "label_text_length": 10,
            "data_density_by_region": {
                "upper_left": 0.3, "upper_right": 0.1,
                "lower_left": 0.5, "lower_right": 0.6,
            },
        },
        "b": {
            "data_element_count": 1,
            "label_text_length": 5,
            "data_density_by_region": {
                "upper_left": 0.2, "upper_right": 0.2,
                "lower_left": 0.3, "lower_right": 0.3,
            },
        },
    }}


def test_report_conforms_to_schema():
    report = analyze_layout(_figure_plan(), _data_characteristics())
    schema = json.loads(schema_path("layout-analysis.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(report))


def test_panel_width_proportional_to_data_element_count():
    report = analyze_layout(_figure_plan(), _data_characteristics())
    recs = {r["panel_id"]: r for r in report["panel_width_recommendations"]}
    # Panel a has 3 elements, panel b has 1 -> a should get more width.
    assert recs["a"]["recommended_ratio"] > recs["b"]["recommended_ratio"]


def test_label_text_length_increases_recommended_width():
    chars_long = _data_characteristics(panels={
        "a": {"data_element_count": 1, "label_text_length": 40,
              "data_density_by_region": {"upper_left": 0.1, "upper_right": 0.1,
                                         "lower_left": 0.1, "lower_right": 0.1}},
        "b": {"data_element_count": 1, "label_text_length": 3,
              "data_density_by_region": {"upper_left": 0.1, "upper_right": 0.1,
                                         "lower_left": 0.1, "lower_right": 0.1}},
    })
    report = analyze_layout(_figure_plan(), chars_long)
    recs = {r["panel_id"]: r for r in report["panel_width_recommendations"]}
    # Long labels need more width.
    assert recs["a"]["recommended_ratio"] > recs["b"]["recommended_ratio"]


def test_legend_recommended_in_emptiest_region():
    report = analyze_layout(_figure_plan(), _data_characteristics())
    for rec in report["legend_placement_recommendations"]:
        candidates = rec["candidates"]
        recommended = [c for c in candidates if c.get("is_recommended")]
        assert len(recommended) == 1
        # The recommended candidate should have the lowest density score.
        min_density = min(c["density_score"] for c in candidates)
        assert recommended[0]["density_score"] == min_density


def test_warning_when_no_viable_in_plot_legend():
    # All four regions have high density -> no viable in-plot position.
    dense = _data_characteristics(panels={
        "a": {"data_element_count": 10, "label_text_length": 20,
              "data_density_by_region": {
                  "upper_left": 0.9, "upper_right": 0.9,
                  "lower_left": 0.9, "lower_right": 0.9}},
    })
    plan = _figure_plan(panels=[{"panel_id": "a", "bbox": [0, 0, 1, 1],
                                "physical_size": [90, 112.5]}])
    report = analyze_layout(plan, dense)
    assert any("no viable" in w.lower() or "external" in w.lower()
               for w in report["warnings"])


def test_warning_when_too_many_elements_for_width():
    # Many elements in a narrow panel.
    crowded = _data_characteristics(panels={
        "a": {"data_element_count": 20, "label_text_length": 5,
              "data_density_by_region": {
                  "upper_left": 0.5, "upper_right": 0.5,
                  "lower_left": 0.5, "lower_right": 0.5}},
    })
    plan = _figure_plan(panels=[{"panel_id": "a", "bbox": [0, 0, 0.2, 1],
                                "physical_size": [36, 112.5]}])
    report = analyze_layout(plan, crowded)
    assert len(report["warnings"]) >= 1


def test_no_legend_recommendation_for_single_element_panels():
    # A panel with only 1 data element likely doesn't need a legend.
    chars = _data_characteristics(panels={
        "a": {"data_element_count": 1, "label_text_length": 5,
              "data_density_by_region": {
                  "upper_left": 0.1, "upper_right": 0.1,
                  "lower_left": 0.1, "lower_right": 0.1}},
    })
    plan = _figure_plan(panels=[{"panel_id": "a", "bbox": [0, 0, 1, 1],
                                "physical_size": [180, 112.5]}])
    report = analyze_layout(plan, chars)
    # Panels with <=1 data element don't need legend placement.
    panel_ids = {r["panel_id"] for r in report["legend_placement_recommendations"]}
    assert "a" not in panel_ids
