"""Render semantic composition regions without implying editable raster internals."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from figure_tools.vector.primitives import SvgCanvas


def render_composition_blueprint(
    composition: Mapping[str, Any],
    semantic_graph: Mapping[str, Any],
    canvas: Mapping[str, Any],
) -> str:
    width = float(canvas["width"])
    height = float(canvas["height"])
    svg = SvgCanvas(width, height)
    svg.rect(0, 0, width, height, fill="#FFFFFF", stroke="#D7DCE8", stroke_width=0.6)
    anchors: dict[str, tuple[float, float]] = {}
    colors = ("#EEF2FF", "#ECFEFF", "#F0FDFA")
    forbidden = " ".join(
        str(item).lower() for item in composition.get("forbidden_patterns", [])
    )
    avoid_boxes = "card" in forbidden or "box" in forbidden
    avoid_arrows = "arrow" in forbidden
    for index, region in enumerate(composition.get("regions", [])):
        x, y, region_width, region_height = [float(value) for value in region["bbox"]]
        rx, ry = x * width, y * height
        rw, rh = region_width * width, region_height * height
        if avoid_boxes:
            svg.path(
                f"M {rx} {ry + rh * 0.2} C {rx + rw * 0.3} {ry}, "
                f"{rx + rw * 0.7} {ry + rh * 0.08}, {rx + rw} {ry + rh * 0.2} "
                f"L {rx + rw} {ry + rh * 0.8} C {rx + rw * 0.7} {ry + rh}, "
                f"{rx + rw * 0.3} {ry + rh * 0.92}, {rx} {ry + rh * 0.8} Z",
                fill=colors[index % len(colors)], stroke="#64748B",
                stroke_width=0.45, data_region_id=region["region_id"],
            )
        else:
            svg.rect(
                rx, ry, rw, rh,
                fill=colors[index % len(colors)], stroke="#64748B",
                stroke_width=0.65, stroke_dasharray="4 3",
                data_region_id=region["region_id"],
            )
        svg.text(
            rx + 3, ry + 10, region["label"], font_size=7,
            fill="#334155", data_region_id=region["region_id"],
        )
        node_ids = [str(item) for item in region.get("node_ids", [])]
        for node_index, node_id in enumerate(node_ids):
            fraction = (node_index + 1) / (len(node_ids) + 1)
            ax = rx + rw * fraction
            wave = ((node_index % 3) - 1) * min(5.0, rh * 0.08)
            ay = ry + rh * 0.52 + wave
            anchors[node_id] = (ax, ay)
            svg.circle(
                ax, ay, 1.8, fill="#2563EB", stroke="none",
                data_node_id=node_id,
            )
            svg.text(
                ax + 2.5, ay - 2, node_id, font_size=5.5,
                fill="#475569", data_node_id=node_id,
            )
    port_nodes = {
        str(port["port_id"]): str(port["node_id"])
        for port in semantic_graph.get("ports", [])
    }
    for edge in semantic_graph.get("typed_edges", []):
        source = anchors.get(port_nodes.get(str(edge["source_port"]), ""))
        target = anchors.get(port_nodes.get(str(edge["target_port"]), ""))
        if source is None or target is None:
            continue
        svg.line(
            source[0], source[1], target[0], target[1],
            stroke="#94A3B8", stroke_width=0.45,
            data_edge_id=edge["edge_id"],
        )
    direction = str(composition.get("reading_direction") or "left_to_right")
    if direction == "left_to_right":
        if avoid_arrows:
            svg.line(
                width * 0.08, height * 0.93, width * 0.92, height * 0.93,
                stroke="#4F46E5", stroke_width=0.8,
                data_reading_direction=direction,
            )
        else:
            svg.arrow(
                width * 0.08, height * 0.93, width * 0.92, height * 0.93,
                stroke="#4F46E5", stroke_width=0.8,
                data_reading_direction=direction,
            )
    svg.text(
        width * 0.08, height * 0.9,
        composition.get("density_flow", "semantic progression"),
        font_size=6, fill="#64748B", data_density_flow="true",
    )
    return svg.to_string()


__all__ = ["render_composition_blueprint"]
