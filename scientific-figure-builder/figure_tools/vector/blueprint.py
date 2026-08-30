"""Render a solved Figure layout as a no-cost editable SVG blueprint."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from figure_tools.vector.primitives import SvgCanvas


def render_figure_blueprint(layout: Mapping[str, Any]) -> str:
    canvas = layout["canvas"]
    width = float(canvas["width"])
    height = float(canvas["height"])
    svg = SvgCanvas(width, height)
    for node in layout.get("nodes", []):
        x, y, node_width, node_height = node["bbox"]
        svg.rect(
            x * width,
            y * height,
            node_width * width,
            node_height * height,
            fill="#F7F7F7",
            stroke="#333333",
            stroke_width=0.75,
            data_node_id=node["node_id"],
        )
        svg.text(
            x * width + 2,
            y * height + 8,
            node["node_id"],
            font_size=7,
            fill="#111111",
            data_node_id=node["node_id"],
        )
    for connector in layout.get("connectors", []):
        source_x, source_y = connector["source"]
        target_x, target_y = connector["target"]
        svg.arrow(
            source_x * width,
            source_y * height,
            target_x * width,
            target_y * height,
            stroke="#333333",
            stroke_width=0.75,
            data_edge_id=connector["edge_id"],
        )
    return svg.to_string()


__all__ = ["render_figure_blueprint"]
