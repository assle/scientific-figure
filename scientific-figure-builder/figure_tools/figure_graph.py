"""Build and validate the scientific structure carried by a Figure plan."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def _absolute_bbox(asset: Mapping[str, Any], panels: Mapping[str, Mapping[str, Any]]):
    bbox = [float(value) for value in asset.get("bbox", [0, 0, 1, 1])]
    if asset.get("bbox_space") != "panel":
        return bbox
    panel = panels[str(asset["panel_id"])]
    px, py, pw, ph = (float(value) for value in panel["bbox"])
    x, y, width, height = bbox
    return [
        round(px + x * pw, 12),
        round(py + y * ph, 12),
        round(width * pw, 12),
        round(height * ph, 12),
    ]


def build_figure_graph(
    request: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a versioned graph with addressable nodes, ports, and relations."""

    panels = {str(item["panel_id"]): item for item in plan.get("panels", [])}
    nodes = [
        {
            "node_id": str(asset["asset_id"]),
            "node_type": str(asset["type"]),
            "asset_id": str(asset["asset_id"]),
            "panel_id": str(asset.get("panel_id") or ""),
            "bbox": _absolute_bbox(asset, panels),
        }
        for asset in plan.get("assets", [])
        if asset.get("panel_id") and asset.get("bbox")
    ]
    node_ids = {item["node_id"] for item in nodes}
    supplied = request.get("figure_graph")
    graph_input = dict(supplied) if isinstance(supplied, Mapping) else {}
    ports = [copy.deepcopy(dict(item)) for item in graph_input.get("ports", [])]
    nodes_with_ports = {str(item.get("node_id")) for item in ports}
    for node_id in sorted(node_ids - nodes_with_ports):
        ports.extend((
            {"port_id": f"{node_id}-in", "node_id": node_id, "side": "left"},
            {"port_id": f"{node_id}-out", "node_id": node_id, "side": "right"},
        ))
    port_ids: set[str] = set()
    for port in ports:
        port_id = str(port.get("port_id") or "")
        node_id = str(port.get("node_id") or "")
        if not port_id or port_id in port_ids:
            raise ValueError(f"duplicate or empty port ID {port_id!r}")
        if node_id not in node_ids:
            raise ValueError(f"port {port_id!r} references unknown node {node_id!r}")
        port_ids.add(port_id)
    edges = [
        copy.deepcopy(dict(item)) for item in graph_input.get("typed_edges", [])
    ]
    edge_ids: set[str] = set()
    for edge in edges:
        edge_id = str(edge.get("edge_id") or "")
        if not edge_id or edge_id in edge_ids:
            raise ValueError(f"duplicate or empty edge ID {edge_id!r}")
        source = str(edge.get("source_port") or "")
        target = str(edge.get("target_port") or "")
        if source not in port_ids:
            raise ValueError(f"edge {edge_id!r} references unknown source port {source!r}")
        if target not in port_ids:
            raise ValueError(f"edge {edge_id!r} references unknown target port {target!r}")
        edge_ids.add(edge_id)
    return {
        "schema_version": "1.0",
        "figure_id": str(plan["figure_id"]),
        "nodes": nodes,
        "ports": ports,
        "typed_edges": edges,
        "groups": [
            copy.deepcopy(dict(item)) for item in graph_input.get("groups", [])
        ],
        "labels": [
            copy.deepcopy(dict(item)) for item in graph_input.get("labels", [])
        ],
        "constraints": [
            copy.deepcopy(dict(item)) for item in graph_input.get("constraints", [])
        ],
    }


__all__ = ["build_figure_graph"]
