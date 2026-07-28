"""Figure-plan builder (plan sections 4, 7, 15).

Consumes a structured request (the OpenCode planning model turns natural
language into this structure) and emits a figure_plan.json that conforms to the
v1 schema.
"""

from __future__ import annotations

from typing import Any

from figure_tools.planning.router import route_element

_ELEMENT_TYPE_TO_ASSET_TYPE = {
    "data_plot": "data_plot",
    "image_asset": "image_asset",
    "label": "text",
    "annotation": "text",
    "text": "text",
    "equation": "equation",
    "vector_element": "vector_element",
}


def _planned_assets(request: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    z = 1
    for panel in request.get("panels", []):
        for el in panel.get("elements", []):
            assets.append({
                "asset_id": el["element_id"],
                "type": _ELEMENT_TYPE_TO_ASSET_TYPE[el["type"]],
                "z_order": z,
                "dependencies": [],
                "routing": route_element(el),
            })
            z += 1
    for label in request.get("labels", []):
        assets.append({
            "asset_id": label["element_id"],
            "type": _ELEMENT_TYPE_TO_ASSET_TYPE.get(label["kind"], "text"),
            "z_order": z,
            "dependencies": [],
            "routing": "svg",
        })
        z += 1
    return assets


def _estimated_paid_calls(request: dict[str, Any], assets: list[dict]) -> dict[str, int]:
    n_ai = sum(1 for a in assets if a["type"] == "image_asset")
    return {
        "reference_analysis": 1 if request.get("reference_figures") else 0,
        "generation": n_ai,
        "edits": 0,
        "validations": n_ai,
        "final_validation": 1,
    }


def _planned_uploads(request: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"path": p, "reason": "reference analysis"}
        for p in request.get("reference_figures", [])
    ]


def _approval_status(request: dict[str, Any]) -> str:
    return "auto_execute" if request.get("auto_execute") else "pending"


def create_figure_plan(
    request: dict[str, Any],
    style_bible_ref: str = "default",
) -> dict[str, Any]:
    assets = _planned_assets(request)
    figure_id = request["figure_id"]
    run_id = request.get("run_id", figure_id)
    return {
        "schema_version": "1.0",
        "figure_id": figure_id,
        "run_id": run_id,
        "canvas": request["canvas"],
        "units": request.get("units", "mm"),
        "panels": [
            {
                "panel_id": p["panel_id"],
                "bbox": p["bbox"],
                "physical_size": p["physical_size"],
            }
            for p in request.get("panels", [])
        ],
        "assets": assets,
        "style_bible_ref": style_bible_ref,
        "text_elements": [
            {"element_id": l["element_id"], "kind": l.get("kind", "label"),
             "content": l["content"]}
            for l in request.get("labels", [])
        ],
        "assumptions": list(request.get("assumptions", [])),
        "uncertainties": list(request.get("uncertainties", [])),
        "user_input_requirements": list(request.get("user_input_requirements", [])),
        "estimated_paid_calls": _estimated_paid_calls(request, assets),
        "planned_uploads": _planned_uploads(request),
        "approval": {"status": _approval_status(request)},
    }
