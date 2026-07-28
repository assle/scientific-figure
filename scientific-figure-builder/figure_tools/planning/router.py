"""Task classification and element routing (plan sections 2, 4, 15)."""

from __future__ import annotations

from typing import Any

_ELEMENT_ROUTING = {
    "data_plot": "python",
    "image_asset": "ark_image",
    "label": "svg",
    "annotation": "svg",
    "text": "svg",
    "equation": "svg",
    "vector_element": "svg",
}


def route_element(element: dict[str, Any]) -> str:
    etype = element["type"]
    if etype not in _ELEMENT_ROUTING:
        raise ValueError(f"no routing for element type {etype!r}")
    return _ELEMENT_ROUTING[etype]


def _element_types(request: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for panel in request.get("panels", []):
        for el in panel.get("elements", []):
            types.add(el["type"])
    return types


def classify_task(request: dict[str, Any]) -> str:
    types = _element_types(request)
    has_data = "data_plot" in types
    has_ai = "image_asset" in types
    if request.get("reference_figures"):
        return "figure_decomposition"
    if has_data and has_ai:
        return "hybrid"
    if has_data:
        return "data_plot"
    return "schematic"
