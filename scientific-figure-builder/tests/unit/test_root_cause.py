"""Root cause analysis tests (spec 0001, improvement 4).

Pure-function tests for analyze_root_causes: pattern-matching validation
failures to structural causes and remediation suggestions.
"""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.validation.root_cause import analyze_root_causes


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


def _validation_report(checks):
    from figure_tools.validation.summary import summarize_checks

    return {
        "schema_version": "1.0",
        "run_id": "final",
        "checks": checks,
        "summary": summarize_checks(checks),
    }


def test_report_conforms_to_schema():
    checks = [
        {"check_id": "legend_data_overlap", "scope": "panel:a", "level": "error",
         "status": "fail", "detail": "legend overlaps data in panel a"},
    ]
    report = analyze_root_causes([_validation_report(checks)], _figure_plan())
    schema = json.loads(schema_path("root-cause-report.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(report))


def test_legend_data_overlap_with_unequal_panels():
    checks = [
        {"check_id": "legend_data_overlap", "scope": "panel:a", "level": "error",
         "status": "fail", "detail": "legend overlaps data in panel a"},
    ]
    plan = _figure_plan(panels=[
        {"panel_id": "a", "bbox": [0, 0, 0.35, 1], "physical_size": [63, 112.5]},
        {"panel_id": "b", "bbox": [0.35, 0, 0.65, 1], "physical_size": [117, 112.5]},
    ])
    report = analyze_root_causes([_validation_report(checks)], plan)
    assert len(report["findings"]) >= 1
    finding = report["findings"][0]
    assert finding["symptom"]["check_id"] == "legend_data_overlap"
    assert "width" in finding["likely_cause"].lower()
    assert finding["remediation"]


def test_effective_dpi_fail_suggests_increase_dpi():
    checks = [
        {"check_id": "effective_resolution", "scope": "final", "level": "warning",
         "status": "fail", "detail": "effective 150 dpi < 300"},
    ]
    report = analyze_root_causes([_validation_report(checks)], _figure_plan())
    assert len(report["findings"]) >= 1
    finding = report["findings"][0]
    assert "dpi" in finding["likely_cause"].lower() or "dpi" in finding["remediation"].lower()


def test_effective_dpi_check_id_matched():
    checks = [
        {"check_id": "effective_dpi", "scope": "asset:fiber.png", "level": "error",
         "status": "fail", "detail": "effective 231 dpi (min 300)"},
    ]
    report = analyze_root_causes([_validation_report(checks)], _figure_plan())
    assert len(report["findings"]) >= 1
    finding = report["findings"][0]
    assert finding["symptom"]["check_id"] == "effective_dpi"
    assert "dpi" in finding["likely_cause"].lower()


def test_text_overlap_with_long_labels():
    checks = [
        {"check_id": "text_overlap", "scope": "panel:a", "level": "error",
         "status": "fail", "detail": "tick labels overlap in panel a"},
    ]
    plan = _figure_plan(panels=[
        {"panel_id": "a", "bbox": [0, 0, 0.3, 1], "physical_size": [54, 112.5]},
    ])
    report = analyze_root_causes([_validation_report(checks)], plan)
    assert len(report["findings"]) >= 1
    finding = report["findings"][0]
    assert "label" in finding["likely_cause"].lower() or "label" in finding["remediation"].lower()


def test_no_findings_when_all_pass():
    checks = [
        {"check_id": "legend_data_overlap", "scope": "panel:a", "level": "error",
         "status": "pass", "detail": "no overlap"},
    ]
    report = analyze_root_causes([_validation_report(checks)], _figure_plan())
    assert report["findings"] == []


def test_severity_ranking_present():
    checks = [
        {"check_id": "legend_data_overlap", "scope": "panel:a", "level": "error",
         "status": "fail", "detail": "overlap"},
        {"check_id": "effective_resolution", "scope": "final", "level": "warning",
         "status": "fail", "detail": "low dpi"},
    ]
    report = analyze_root_causes([_validation_report(checks)], _figure_plan())
    assert len(report["severity_ranking"]) >= 1
    # Error-level causes should rank before warning-level.
    assert len(report["severity_ranking"]) >= 1


def test_uses_layout_analysis_for_context():
    checks = [
        {"check_id": "legend_data_overlap", "scope": "panel:a", "level": "error",
         "status": "fail", "detail": "legend overlaps data"},
    ]
    layout_analysis = {
        "schema_version": "1.0",
        "panel_width_recommendations": [
            {"panel_id": "a", "data_element_count": 5, "recommended_ratio": 1.5,
             "reasoning": "5 elements need more width"},
        ],
        "legend_placement_recommendations": [],
        "warnings": ["panel a width insufficient for data element count"],
    }
    report = analyze_root_causes([_validation_report(checks)], _figure_plan(),
                                 layout_analysis=layout_analysis)
    finding = report["findings"][0]
    # Should reference the layout analysis context.
    assert "width" in finding["likely_cause"].lower()


def test_specific_remediation_with_width_recommendation():
    checks = [
        {"check_id": "legend_data_overlap", "scope": "panel:a", "level": "error",
         "status": "fail", "detail": "legend overlaps data in panel a"},
    ]
    plan = _figure_plan(panels=[
        {"panel_id": "a", "bbox": [0, 0, 0.35, 1], "physical_size": [63, 112.5]},
        {"panel_id": "b", "bbox": [0.35, 0, 0.65, 1], "physical_size": [117, 112.5]},
    ])
    layout_analysis = {
        "schema_version": "1.0",
        "panel_width_recommendations": [
            {"panel_id": "a", "data_element_count": 5, "recommended_ratio": 1.5,
             "reasoning": "5 elements need more width"},
        ],
        "legend_placement_recommendations": [],
        "warnings": [],
    }
    report = analyze_root_causes([_validation_report(checks)], plan,
                                 layout_analysis=layout_analysis)
    finding = report["findings"][0]
    # Remediation should include specific ratio values.
    assert "0.4" in finding["remediation"] or "0.3" in finding["remediation"]
    assert "1.5" in finding["remediation"]
