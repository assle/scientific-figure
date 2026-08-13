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

DEFAULT_FIGURE_WIDTHS_CM = {
    "half_column": 6.5,
    "full_column": 14.0,
}
DEFAULT_CANVAS_MM = {"width": 180.0, "height": 90.0}
DEFAULT_LANGUAGE = "zh"
DEFAULT_STYLE = "default"


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


def _output_target_requirements(request: dict[str, Any]) -> list[str]:
    """Ask for the output target when the request does not specify it.

    ``export_target`` is intentionally a required clarification, not a silent
    default, so the planning model must surface the question to the user before
    generating a plan that triggers paid work.
    """
    if request.get("export_target"):
        return []
    return [
        "Confirm the output target: general (PNG/SVG/PDF) or ppt "
        "(editable PowerPoint-friendly SVG, usually with optional PPTX)."
    ]


def _figure_width_requirements(request: dict[str, Any]) -> list[str]:
    """Ask for the figure width when it is not explicitly selected.

    The default widths follow common journal column sizes: half-column 6.5 cm
    and full-column 14 cm. The height should be derived from the configured
    canvas aspect ratio after the user selects the width.
    """
    if request.get("figure_width_cm") is not None:
        return []
    half = DEFAULT_FIGURE_WIDTHS_CM["half_column"]
    full = DEFAULT_FIGURE_WIDTHS_CM["full_column"]
    return [
        f"Confirm figure width: half-column {half} cm or full-column {full} cm "
        "(半栏图 6.5 cm / 通栏图 14 cm)."
    ]


def _language_requirements(request: dict[str, Any]) -> list[str]:
    """Ask for the figure text language when it is not explicitly selected."""
    if request.get("language"):
        return []
    return [
        "Confirm the figure text language: Chinese (zh) or English (en) "
        "(图内文字用中文还是英文？)."
    ]


def _style_requirements(request: dict[str, Any]) -> list[str]:
    """Ask for the visual style when it is not explicitly selected."""
    if request.get("style"):
        return []
    return [
        "Confirm the figure style: default publication style or a custom "
        "style reference (默认出版风还是自定义参考风格？)."
    ]


def collect_required_clarifications(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return unresolved required questions that must be answered by the user.

    Unlike ``create_figure_plan`` (which only records questions as strings),
    this is the hard gate: no rendering, generation, assembly, or export may
    happen while this list is non-empty. Defaults are advisory only; the agent
    must still ask first.
    """
    checks = (
        ("export_target", _output_target_requirements(request), "general"),
        ("figure_width_cm", _figure_width_requirements(request), 6.5),
        ("language", _language_requirements(request), DEFAULT_LANGUAGE),
        ("style", _style_requirements(request), DEFAULT_STYLE),
    )
    clarifications: list[dict[str, Any]] = []
    for field, questions, default in checks:
        if questions:
            clarifications.append({
                "field": field,
                "question": questions[0],
                "default": default,
            })
    return clarifications


def resolve_figure_canvas(
    request: dict[str, Any],
    default_canvas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve canvas dimensions from an explicit width or the request canvas.

    If ``figure_width_cm`` is present it wins over ``request["canvas"]``, and
    the height is derived from the default canvas aspect ratio.
    """
    defaults = default_canvas or DEFAULT_CANVAS_MM
    width_cm = request.get("figure_width_cm")
    if width_cm is None:
        if not request.get("canvas"):
            raise ValueError("request must include canvas or figure_width_cm")
        return request["canvas"]

    aspect_ratio = float(defaults["width"]) / float(defaults["height"])
    width_mm = float(width_cm) * 10.0
    height_mm = width_mm / aspect_ratio
    return {
        "aspect_ratio": aspect_ratio,
        "width": width_mm,
        "height": height_mm,
    }


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
        "canvas": resolve_figure_canvas(request),
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
        "user_input_requirements": [
            *list(request.get("user_input_requirements", [])),
            *_output_target_requirements(request),
            *_figure_width_requirements(request),
            *_language_requirements(request),
            *_style_requirements(request),
        ],
        "estimated_paid_calls": _estimated_paid_calls(request, assets),
        "planned_uploads": _planned_uploads(request),
        "approval": {"status": _approval_status(request)},
    }
