"""Schema-shaped suggestions returned by the Planning Phase worker."""

from __future__ import annotations

from typing import Any, Mapping

from figure_tools.generation_intent import resolve_units


def _composition(brief: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(brief.get("request") or {})
    members: list[str] = []
    for unit in resolve_units(request):
        if unit["method"] == "image_model":
            members.extend(str(item) for item in unit["members"])
    if not members:
        return {
            "reading_direction": "left_to_right",
            "density_flow": "balanced",
            "regions": [],
            "forbidden_patterns": [],
        }
    region_count = min(3, len(members))
    regions = []
    for index in range(region_count):
        selected = members[index::region_count]
        gap = 0.025
        width = (1.0 - gap * (region_count + 1)) / region_count
        regions.append({
            "region_id": f"region-{index + 1}",
            "label": f"Visual stage {index + 1}",
            "bbox": [gap + index * (width + gap), 0.08, width, 0.78],
            "node_ids": selected,
            "emphasis": round(0.6 + 0.2 * index / max(region_count - 1, 1), 2),
        })
    return {
        "reading_direction": "left_to_right",
        "density_flow": "semantic progression across a continuous field",
        "regions": regions,
        "forbidden_patterns": [],
    }


def default_planning_advice(brief: Mapping[str, Any]) -> dict[str, Any]:
    """Return the smallest safe Planning Advice for deterministic planning."""

    style_bible = None
    composition = _composition(brief)
    if style_bible is not None:
        composition["forbidden_patterns"] = list(
            style_bible.get("forbidden_elements", [])
        )
    return {
        "schema_version": "1.0",
        "artifact_type": "planning_advice",
        "asset_hints": [],
        "composition": composition,
        "style_bible": style_bible,
    }


__all__ = ["default_planning_advice"]
