"""Root cause analysis for validation failures (spec 0001, improvement 4).

Pattern-matches failed validation checks to structural causes and suggests
remediation.  Uses figure_plan panel geometry and layout_analysis
recommendations to produce specific, actionable suggestions.
Pure function: no external services, no side effects.
"""

from __future__ import annotations

from typing import Any

_CAUSE_PATTERNS: dict[str, dict[str, Any]] = {
    "legend_data_overlap": {
        "likely_cause": "panel width insufficient for data element count; legend placed in high-density region",
        "remediation": "increase the affected panel's width ratio and move the legend to the emptiest region",
    },
    "text_overlap": {
        "likely_cause": "tick labels too long for the allocated panel width",
        "remediation": "abbreviate labels, split across two lines, rotate ticks, or widen the panel",
    },
    "effective_resolution": {
        "likely_cause": "low effective DPI, likely caused by bbox_inches='tight' shrinking the output or insufficient savefig dpi",
        "remediation": "increase savefig dpi and/or set bbox_inches=None to preserve physical dimensions",
    },
    "effective_dpi": {
        "likely_cause": "low effective DPI for the asset at its physical size",
        "remediation": "regenerate at higher resolution or increase savefig dpi",
    },
    "label_readability": {
        "likely_cause": "axis tick labels are too small or too crowded for the panel size",
        "remediation": "increase font size, reduce tick frequency, or widen the panel",
    },
    "missing_assets": {
        "likely_cause": "one or more assets failed to render or were not found",
        "remediation": "check the render error reports for the failing assets and fix the source data or spec",
    },
    "alpha_for_ai_assets": {
        "likely_cause": "AI-generated asset lacks a real alpha channel after background removal",
        "remediation": "regenerate the asset or manually repair the transparency mask",
    },
}


def analyze_root_causes(
    validation_reports: list[dict[str, Any]],
    figure_plan: dict[str, Any],
    layout_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed = _collect_failed_checks(validation_reports)
    if not failed:
        return {"schema_version": "1.0", "findings": [], "severity_ranking": []}

    panel_widths = _panel_bbox_widths(figure_plan)
    width_recs = _width_recs_by_panel(layout_analysis)

    findings: list[dict[str, Any]] = []
    for check in failed:
        pattern = _CAUSE_PATTERNS.get(check.get("check_id", ""))
        if pattern is None:
            continue
        cause, remediation = _augment(pattern, check, panel_widths, width_recs,
                                      layout_analysis)
        findings.append({
            "symptom": {"check_id": check["check_id"],
                        "detail": check.get("detail", "")},
            "likely_cause": cause,
            "remediation": remediation,
        })

    return {
        "schema_version": "1.0",
        "findings": findings,
        "severity_ranking": _rank_by_severity(findings, validation_reports),
    }


def _collect_failed_checks(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for r in reports for c in r.get("checks", []) if c.get("status") == "fail"]


def _panel_bbox_widths(figure_plan: dict[str, Any]) -> dict[str, float]:
    return {p["panel_id"]: p.get("bbox", [0, 0, 1, 1])[2]
            for p in figure_plan.get("panels", [])}


def _width_recs_by_panel(
    layout_analysis: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if layout_analysis is None:
        return {}
    return {r["panel_id"]: r
            for r in layout_analysis.get("panel_width_recommendations", [])}


def _extract_panel_id(scope: str) -> str | None:
    if "panel:" in scope:
        return scope.split("panel:")[1].split(",")[0].strip()
    return None


def _augment(
    pattern: dict[str, Any],
    check: dict[str, Any],
    panel_widths: dict[str, float],
    width_recs: dict[str, dict[str, Any]],
    layout_analysis: dict[str, Any] | None,
) -> tuple[str, str]:
    cause = pattern["likely_cause"]
    remediation = pattern["remediation"]
    cid = check.get("check_id", "")
    scope = check.get("scope", "")
    pid = _extract_panel_id(scope)

    if cid == "legend_data_overlap" and pid and panel_widths:
        cause, remediation = _legend_overlap_cause(pid, panel_widths, width_recs)
    elif cid == "text_overlap" and pid and panel_widths:
        cause, remediation = _text_overlap_cause(pid, panel_widths, width_recs)
    elif cid in ("effective_resolution", "effective_dpi"):
        cause, remediation = _dpi_cause(check, cid)

    if layout_analysis:
        for w in layout_analysis.get("warnings", []):
            if pid and pid in w:
                cause = w
                break

    return cause, remediation


def _legend_overlap_cause(
    pid: str,
    panel_widths: dict[str, float],
    width_recs: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    this_width = panel_widths.get(pid, 0)
    max_width = max(panel_widths.values()) if panel_widths else 1
    rec = width_recs.get(pid)
    if rec and rec["recommended_ratio"] > this_width:
        return (
            f"panel {pid} width ({this_width:.2f}) insufficient for "
            f"{rec['data_element_count']} data elements",
            f"increase panel {pid} width ratio from {this_width:.1f} to "
            f"{rec['recommended_ratio']:.1f} and move legend to the emptiest region",
        )
    if this_width < max_width * 0.7:
        return (
            f"panel {pid} width ({this_width:.2f}) is significantly narrower than "
            f"the widest panel ({max_width:.2f}); legend has no room",
            f"increase panel {pid} width ratio to at least {max_width:.1f}",
        )
    return (
        f"legend in panel {pid} overlaps data in a high-density region",
        f"move legend to a lower-density region in panel {pid}",
    )


def _text_overlap_cause(
    pid: str,
    panel_widths: dict[str, float],
    width_recs: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    this_width = panel_widths.get(pid, 0)
    rec = width_recs.get(pid)
    if rec and rec.get("data_element_count", 0) > 3:
        return (
            f"panel {pid} has {rec['data_element_count']} data elements in "
            f"{this_width:.2f} normalized width; tick labels collide",
            f"widen panel {pid} or abbreviate labels to reduce text overlap",
        )
    return (
        f"tick labels in panel {pid} are too long for the panel width",
        "abbreviate labels, split across two lines, or rotate ticks",
    )


def _dpi_cause(check: dict[str, Any], cid: str) -> tuple[str, str]:
    detail = check.get("detail", "")
    if cid == "effective_dpi":
        return (
            f"asset effective DPI below minimum ({detail})",
            "regenerate at higher resolution or increase savefig dpi",
        )
    return (
        f"low effective DPI ({detail}); likely bbox_inches='tight' shrinking output",
        "increase savefig dpi and/or set bbox_inches=None to preserve dimensions",
    )


def _rank_by_severity(
    findings: list[dict[str, Any]],
    validation_reports: list[dict[str, Any]],
) -> list[str]:
    error_cids = {c["check_id"] for r in validation_reports
                  for c in r.get("checks", [])
                  if c.get("level") == "error" and c.get("status") == "fail"}
    error_causes = [f["likely_cause"] for f in findings
                    if f["symptom"]["check_id"] in error_cids]
    warning_causes = [f["likely_cause"] for f in findings
                      if f["symptom"]["check_id"] not in error_cids]
    return error_causes + warning_causes
