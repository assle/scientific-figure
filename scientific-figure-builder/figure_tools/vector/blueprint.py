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
    for group in layout.get("groups", []):
        if not group.get("bbox"):
            continue
        x, y, group_width, group_height = group["bbox"]
        svg.rect(
            x * width,
            y * height,
            group_width * width,
            group_height * height,
            fill="none",
            stroke="#777777",
            stroke_width=0.75,
            stroke_dasharray="3 2",
            data_group_id=group.get("group_id", "group"),
        )
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
        points = connector.get("points") or [
            connector["source"], connector["target"]
        ]
        scaled = [(point[0] * width, point[1] * height) for point in points]
        if len(scaled) > 2:
            svg.polyline(
                scaled[:-1],
                fill="none",
                stroke="#333333",
                stroke_width=0.75,
                data_edge_id=connector["edge_id"],
            )
        source_x, source_y = scaled[-2]
        target_x, target_y = scaled[-1]
        svg.arrow(
            source_x,
            source_y,
            target_x,
            target_y,
            stroke="#333333",
            stroke_width=0.75,
            data_edge_id=connector["edge_id"],
        )
    return svg.to_string()


__all__ = ["render_figure_blueprint"]
