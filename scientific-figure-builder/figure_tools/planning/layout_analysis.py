"""Pre-render layout analysis (spec 0001, improvement 2).

Pure-function module that analyses data characteristics and panel geometry
*before* rendering to recommend panel width ratios and legend placements.
No external services, no side effects.
"""

from __future__ import annotations

from typing import Any

_POSITIONS = ("upper_left", "upper_right", "lower_left", "lower_right")
_DENSITY_THRESHOLD = 0.7
_LABEL_LENGTH_THRESHOLD = 15
_MAX_ELEMENTS_PER_UNIT_WIDTH = 8


def analyze_layout(
    figure_plan: dict[str, Any],
    data_characteristics: dict[str, Any],
) -> dict[str, Any]:
    panels = figure_plan.get("panels", [])
    chars_by_panel = data_characteristics.get("panels", {})

    width_recs: list[dict[str, Any]] = []
    legend_recs: list[dict[str, Any]] = []
    warnings: list[str] = []

    for panel in panels:
        pid = panel["panel_id"]
        info = chars_by_panel.get(pid, {})
        element_count = info.get("data_element_count", 0)
        label_len = info.get("label_text_length", 0)
        densities = info.get("data_density_by_region", {})

        width_recs.append(_width_recommendation(pid, element_count, label_len))
        _check_width_sufficiency(panel, element_count, warnings)
        _check_legend_placement(pid, element_count, densities, legend_recs, warnings)

    return {
        "schema_version": "1.0",
        "panel_width_recommendations": width_recs,
        "legend_placement_recommendations": legend_recs,
        "warnings": warnings,
    }


def _width_recommendation(
    pid: str, element_count: int, label_len: int,
) -> dict[str, Any]:
    ratio = float(max(element_count, 1))
    reasoning_parts = [f"{element_count} data elements"]
    if label_len > _LABEL_LENGTH_THRESHOLD:
        ratio *= 1.2
        reasoning_parts.append(f"long labels ({label_len} chars) increase width need")
    return {
        "panel_id": pid,
        "data_element_count": element_count,
        "recommended_ratio": round(ratio, 2),
        "reasoning": "; ".join(reasoning_parts) + "; proportional allocation",
    }


def _check_width_sufficiency(
    panel: dict[str, Any], element_count: int, warnings: list[str],
) -> None:
    bbox = panel.get("bbox", [0, 0, 1, 1])
    panel_width = bbox[2] if len(bbox) >= 4 else 1.0
    if panel_width <= 0:
        return
    elements_per_unit = element_count / panel_width
    if elements_per_unit > _MAX_ELEMENTS_PER_UNIT_WIDTH:
        warnings.append(
            f"panel {panel['panel_id']} has {element_count} data elements in "
            f"{panel_width:.2f} normalized width ({elements_per_unit:.1f}/unit); "
            "consider widening the panel or using an external legend"
        )


def _check_legend_placement(
    pid: str,
    element_count: int,
    densities: dict[str, float],
    legend_recs: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    if element_count <= 1:
        return

    candidates: list[dict[str, Any]] = []
    for pos in _POSITIONS:
        score = densities.get(pos, 0.5)
        candidates.append({"position": pos, "density_score": score,
                           "is_recommended": False})

    best = min(candidates, key=lambda c: c["density_score"])
    best["is_recommended"] = True
    legend_recs.append({"panel_id": pid, "candidates": candidates})

    all_dense = all(c["density_score"] >= _DENSITY_THRESHOLD for c in candidates)
    if all_dense:
        warnings.append(
            f"panel {pid} has no viable in-plot legend position "
            f"(all regions >= {_DENSITY_THRESHOLD} density); "
            "use an external legend or adjust the layout"
        )
