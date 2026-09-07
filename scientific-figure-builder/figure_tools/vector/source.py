"""Input contract for locally rendered vector elements."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET


def svg_source(element: dict[str, Any]) -> str:
    """Require SVG source, never silently treat a description as artwork."""
    content = element.get("content")
    try:
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        root = ET.fromstring(content)
        if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
            raise ValueError("root must be svg")
    except (ET.ParseError, ValueError) as exc:
        raise ValueError(
            f"{element.get('element_id', 'vector_element')}: content must contain "
            "valid SVG source (<svg>...</svg>). Convert the description to SVG "
            "before submitting; use image_asset only when image generation is intended."
        ) from exc
    return content


def validate_vector_inputs(request: dict[str, Any]) -> None:
    for panel in request.get("panels", []):
        for element in panel.get("elements", []):
            if element.get("type") == "vector_element":
                svg_source(element)
