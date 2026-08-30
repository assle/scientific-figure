"""Deterministic placement and port-bound connector solving."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def _port_point(bbox: list[float], side: str) -> list[float]:
    x, y, width, height = bbox
    points = {
        "left": [x, y + height / 2],
        "right": [x + width, y + height / 2],
        "top": [x + width / 2, y],
        "bottom": [x + width / 2, y + height],
        "center": [x + width / 2, y + height / 2],
    }
    if side not in points:
        raise ValueError(f"unsupported port side {side!r}")
    return [round(value, 12) for value in points[side]]


def _overlap(a: list[float], b: list[float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def solve_figure_layout(
    graph: Mapping[str, Any],
    canvas: Mapping[str, Any],
) -> dict[str, Any]:
    nodes = [copy.deepcopy(dict(item)) for item in graph.get("nodes", [])]
    node_by_id = {str(item["node_id"]): item for item in nodes}
    ports = {str(item["port_id"]): item for item in graph.get("ports", [])}
    conflicts: list[dict[str, Any]] = []
    for node in nodes:
        bbox = [float(value) for value in node["bbox"]]
        if (
            len(bbox) != 4
            or bbox[0] < 0
            or bbox[1] < 0
            or bbox[2] <= 0
            or bbox[3] <= 0
            or bbox[0] + bbox[2] > 1
            or bbox[1] + bbox[3] > 1
        ):
            conflicts.append({
                "kind": "node_out_of_bounds",
                "element_ids": [node["node_id"]],
                "detail": "move or resize the node inside the normalized canvas",
            })
    for index, node in enumerate(nodes):
        for other in nodes[index + 1:]:
            if (
                node.get("panel_id") == other.get("panel_id")
                and _overlap(node["bbox"], other["bbox"])
            ):
                conflicts.append({
                    "kind": "node_overlap",
                    "element_ids": [node["node_id"], other["node_id"]],
                    "detail": "separate the overlapping node bounding boxes",
                })
    connectors = []
    for edge in graph.get("typed_edges", []):
        source_port = ports[str(edge["source_port"])]
        target_port = ports[str(edge["target_port"])]
        source_node = node_by_id[str(source_port["node_id"])]
        target_node = node_by_id[str(target_port["node_id"])]
        connectors.append({
            "edge_id": str(edge["edge_id"]),
            "source_port": str(edge["source_port"]),
            "target_port": str(edge["target_port"]),
            "direction": str(edge.get("direction") or "forward"),
            "semantic_type": str(edge.get("semantic_type") or "relation"),
            "source": _port_point(source_node["bbox"], str(source_port["side"])),
            "target": _port_point(target_node["bbox"], str(target_port["side"])),
        })
    return {
        "schema_version": "1.0",
        "figure_id": str(graph["figure_id"]),
        "canvas": copy.deepcopy(dict(canvas)),
        "nodes": nodes,
        "connectors": connectors,
        "groups": [copy.deepcopy(dict(item)) for item in graph.get("groups", [])],
        "labels": [copy.deepcopy(dict(item)) for item in graph.get("labels", [])],
        "conflicts": conflicts,
    }


__all__ = ["solve_figure_layout"]
