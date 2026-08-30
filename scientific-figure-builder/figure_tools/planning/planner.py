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

DEFAULT_CANVAS_MM = {"width": 180.0, "height": 90.0}
DEFAULT_LANGUAGE = "zh"
DEFAULT_STYLE = "default"

# Required clarifications: questions the user must answer before any
# rendering, generation, assembly, or export. They are intentionally
# required — not silent defaults — so the planning model must surface them.
# A field counts as answered when the request carries a non-None value
# (figure_width_cm=0 is a legal width, so None is the only "missing" state).
REQUIRED_CLARIFICATIONS = [
    {
        "field": "export_target",
        "default": "general",
        "question": (
            "Confirm the output target: general (PNG/SVG/PDF) or ppt "
            "(PowerPoint-ready SVG)."
        ),
    },
    {
        "field": "figure_width_cm",
        "default": 6.5,
        "question": (
            "Confirm figure width: half-column 6.5 cm or full-column 14 cm "
            "(半栏图 6.5 cm / 通栏图 14 cm)."
        ),
    },
    {
        "field": "language",
        "default": DEFAULT_LANGUAGE,
        "question": (
            "Confirm the figure text language: Chinese (zh) or English (en) "
            "(图内文字用中文还是英文？)."
        ),
    },
    {
        "field": "style",
        "default": DEFAULT_STYLE,
        "question": (
            "Confirm the figure style: default publication style or a custom "
            "style reference (默认出版风还是自定义参考风格？)."
        ),
    },
]


def _planned_assets(request: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    z = 1
    for panel in request.get("panels", []):
        for el in panel.get("elements", []):
            asset = {
                "asset_id": el["element_id"],
                "type": _ELEMENT_TYPE_TO_ASSET_TYPE[el["type"]],
                "z_order": z,
                "dependencies": [],
                "routing": route_element(el),
                "panel_id": panel["panel_id"],
                "bbox": list(el.get("bbox", panel["bbox"])),
                "physical_size": list(panel["physical_size"]),
                "source": dict(el),
            }
            if el.get("bbox") is not None:
                asset["bbox_space"] = "panel"
            assets.append(asset)
            z += 1
    for label in request.get("labels", []):
        assets.append({
            "asset_id": label["element_id"],
            "type": _ELEMENT_TYPE_TO_ASSET_TYPE.get(label["kind"], "text"),
            "z_order": z,
            "dependencies": [],
            "routing": "svg",
            "source": dict(label),
        })
        z += 1
    return assets


def _estimated_paid_calls(request: dict[str, Any], assets: list[dict]) -> dict[str, int]:
    candidate_calls = sum(
        int((a.get("source") or {}).get("candidate_count", 1))
        for a in assets
        if a["type"] == "image_asset"
    )
    return {
        "reference_analysis": 1 if request.get("reference_figures") else 0,
        "generation": candidate_calls,
        "edits": 0,
        "validations": candidate_calls,
        "final_validation": 1,
    }


def _planned_uploads(request: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"path": p, "reason": "reference analysis"}
        for p in request.get("reference_figures", [])
    ]


def _approval_status(request: dict[str, Any]) -> str:
    return "auto_execute" if request.get("auto_execute") else "pending"


def _unresolved_clarifications(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    """Required clarifications whose field is not answered yet.

    A field counts as answered when the request carries a non-None value.
    """
    return [
        {"field": item["field"], "question": item["question"],
         "default": item["default"]}
        for item in REQUIRED_CLARIFICATIONS
        if request.get(item["field"]) is None
    ]


def collect_required_clarifications(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return unresolved required questions that must be answered by the user.

    This is the hard gate: no rendering, generation, assembly, or export may
    happen while this list is non-empty. Defaults are advisory only; the agent
    must still ask first. ``create_figure_plan`` records the same questions as
    strings; both derive from ``REQUIRED_CLARIFICATIONS``.
    """
    return _unresolved_clarifications(request)


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
    plan = {
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
             "content": l["content"],
             **({"panel_id": l["panel_id"]} if l.get("panel_id") else {})}
            for l in request.get("labels", [])
        ],
        "assumptions": list(request.get("assumptions", [])),
        "uncertainties": list(request.get("uncertainties", [])),
        "user_input_requirements": [
            *list(request.get("user_input_requirements", [])),
            *[c["question"] for c in _unresolved_clarifications(request)],
        ],
        "estimated_paid_calls": _estimated_paid_calls(request, assets),
        "planned_uploads": _planned_uploads(request),
        "approval": {"status": _approval_status(request)},
    }
    export_target = request.get("export_target")
    figure_width_cm = request.get("figure_width_cm")
    include_pptx = request.get("include_pptx")
    if export_target is not None or figure_width_cm is not None or include_pptx is not None:
        plan["delivery"] = {
            key: value
            for key, value in (
                ("export_target", export_target),
                ("figure_width_cm", figure_width_cm),
                ("include_pptx", include_pptx),
            )
            if value is not None
        }
    if request.get("language") is not None:
        plan["language"] = request["language"]
    if request.get("style") is not None:
        plan["style"] = request["style"]
    if request.get("publication_profile") is not None:
        plan["publication_profile"] = request["publication_profile"]
    if request.get("brief_ref") is not None:
        plan["brief_ref"] = request["brief_ref"]
    return plan
