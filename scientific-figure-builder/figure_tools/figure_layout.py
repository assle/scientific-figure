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


def _apply_constraints(
    nodes: list[dict[str, Any]],
    constraints: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(item["node_id"]): item for item in nodes}
    exclusions: list[dict[str, Any]] = []
    for constraint in constraints:
        kind = constraint.get("kind")
        node_ids = [str(item) for item in constraint.get("node_ids", [])]
        selected = [by_id[node_id] for node_id in node_ids if node_id in by_id]
        if kind == "align" and len(selected) > 1:
            axis = str(constraint.get("axis") or "x")
            coordinate = 0 if axis == "x" else 1
            target = selected[0]["bbox"][coordinate]
            for node in selected[1:]:
                node["bbox"][coordinate] = target
        elif kind == "minimum_spacing" and len(selected) > 1:
            axis = str(constraint.get("axis") or "x")
            coordinate = 0 if axis == "x" else 1
            size = 2 if axis == "x" else 3
            gap = float(constraint.get("gap", 0.02))
            for previous, node in zip(selected, selected[1:], strict=False):
                node["bbox"][coordinate] = (
                    previous["bbox"][coordinate] + previous["bbox"][size] + gap
                )
        elif kind == "contain":
            node_id = str(constraint.get("node_id") or "")
            container = [float(value) for value in constraint.get("bbox", [])]
            if node_id in by_id and len(container) == 4:
                node = by_id[node_id]
                x, y, width, height = node["bbox"]
                cx, cy, cw, ch = container
                node["bbox"][0] = min(max(x, cx), cx + cw - width)
                node["bbox"][1] = min(max(y, cy), cy + ch - height)
        elif kind == "exclude":
            exclusions.append(dict(constraint))
    return exclusions


def _solved_groups(
    groups: list[Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    solved = []
    for raw in groups:
        group = copy.deepcopy(dict(raw))
        members = [
            nodes[str(node_id)] for node_id in group.get("node_ids", [])
            if str(node_id) in nodes
        ]
        if members:
            left = min(item["bbox"][0] for item in members)
            top = min(item["bbox"][1] for item in members)
            right = max(item["bbox"][0] + item["bbox"][2] for item in members)
            bottom = max(item["bbox"][1] + item["bbox"][3] for item in members)
            padding = float(group.get("padding", 0.01))
            group["bbox"] = [
                max(0.0, left - padding),
                max(0.0, top - padding),
                min(1.0, right + padding) - max(0.0, left - padding),
                min(1.0, bottom + padding) - max(0.0, top - padding),
            ]
            group["z_order"] = min(int(item.get("z_order", 0)) for item in members) - 1
        solved.append(group)
    return solved


def solve_figure_layout(
    graph: Mapping[str, Any],
    canvas: Mapping[str, Any],
    placement_hints: Mapping[str, list[float]] | None = None,
    panel_hints: Mapping[str, list[float]] | None = None,
) -> dict[str, Any]:
    nodes = [copy.deepcopy(dict(item)) for item in graph.get("nodes", [])]
    hints = placement_hints or {}
    for node in nodes:
        node_id = str(node["node_id"])
        if node_id not in hints:
            raise ValueError(f"missing placement hint for Figure Graph node {node_id!r}")
        node["bbox"] = [float(value) for value in hints[node_id]]
    node_by_id = {str(item["node_id"]): item for item in nodes}
    ports = {str(item["port_id"]): item for item in graph.get("ports", [])}
    conflicts: list[dict[str, Any]] = []
    panel_boxes = {
        str(panel_id): [float(value) for value in bbox]
        for panel_id, bbox in (panel_hints or {}).items()
    }
    for constraint in graph.get("constraints", []):
        if constraint.get("kind") != "panel_size":
            continue
        panel_id = str(constraint.get("panel_id") or "")
        bbox = [float(value) for value in constraint.get("bbox", [])]
        if panel_id and len(bbox) == 4:
            panel_boxes[panel_id] = bbox
    exclusions = _apply_constraints(
        nodes, [dict(item) for item in graph.get("constraints", [])]
    )
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
        panel_bbox = panel_boxes.get(str(node.get("panel_id") or ""))
        if panel_bbox is not None:
            px, py, pw, ph = panel_bbox
            x, y, width, height = node["bbox"]
            if (
                x < px or y < py
                or x + width > px + pw
                or y + height > py + ph
            ):
                conflicts.append({
                    "kind": "node_outside_panel",
                    "element_ids": [node["node_id"]],
                    "detail": "move or resize the node inside its panel",
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
    for exclusion in exclusions:
        excluded_bbox = [float(value) for value in exclusion.get("bbox", [])]
        if len(excluded_bbox) != 4:
            continue
        allowed_nodes = {
            str(item) for item in exclusion.get("node_ids", node_by_id.keys())
        }
        for node_id in sorted(allowed_nodes & node_by_id.keys()):
            if _overlap(node_by_id[node_id]["bbox"], excluded_bbox):
                conflicts.append({
                    "kind": "exclusion_zone_overlap",
                    "element_ids": [node_id],
                    "detail": "move the node outside the declared exclusion zone",
                })
    connectors = []
    for edge in graph.get("typed_edges", []):
        source_port = ports[str(edge["source_port"])]
        target_port = ports[str(edge["target_port"])]
        source_node = node_by_id[str(source_port["node_id"])]
        target_node = node_by_id[str(target_port["node_id"])]
        source = _port_point(source_node["bbox"], str(source_port["side"]))
        target = _port_point(target_node["bbox"], str(target_port["side"]))
        middle_x = round((source[0] + target[0]) / 2, 12)
        points = [source, [middle_x, source[1]], [middle_x, target[1]], target]
        connectors.append({
            "edge_id": str(edge["edge_id"]),
            "source_port": str(edge["source_port"]),
            "target_port": str(edge["target_port"]),
            "direction": str(edge.get("direction") or "forward"),
            "semantic_type": str(edge.get("semantic_type") or "relation"),
            "source": source,
            "target": target,
            "points": points,
        })
    return {
        "schema_version": "1.0",
        "figure_id": str(graph["figure_id"]),
        "canvas": copy.deepcopy(dict(canvas)),
        "panels": [
            {"panel_id": panel_id, "bbox": bbox}
            for panel_id, bbox in sorted(panel_boxes.items())
        ],
        "nodes": nodes,
        "connectors": connectors,
        "groups": _solved_groups(
            [dict(item) for item in graph.get("groups", [])], node_by_id
        ),
        "labels": [copy.deepcopy(dict(item)) for item in graph.get("labels", [])],
        "conflicts": conflicts,
    }


__all__ = ["solve_figure_layout"]
