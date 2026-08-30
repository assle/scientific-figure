from __future__ import annotations

import pytest

from figure_tools.figure_graph import build_figure_graph
from figure_tools.figure_layout import solve_figure_layout
from figure_tools.planning.planner import create_figure_plan
from figure_tools.vector.blueprint import render_figure_blueprint


def _request():
    return {
        "figure_id": "mechanism",
        "canvas": {"aspect_ratio": 2.0, "width": 180, "height": 90},
        "units": "mm",
        "panels": [
            {
                "panel_id": "left",
                "bbox": [0, 0, 0.5, 1],
                "physical_size": [90, 90],
                "elements": [{
                    "element_id": "receptor",
                    "type": "image_asset",
                    "prompt": "receptor",
                    "bbox": [0.1, 0.2, 0.8, 0.6],
                }],
            },
            {
                "panel_id": "right",
                "bbox": [0.5, 0, 0.5, 1],
                "physical_size": [90, 90],
                "elements": [{
                    "element_id": "pathway",
                    "type": "image_asset",
                    "prompt": "pathway",
                    "bbox": [0.1, 0.2, 0.8, 0.6],
                }],
            },
        ],
        "labels": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "figure_graph": {
            "ports": [
                {"port_id": "receptor-out", "node_id": "receptor", "side": "right"},
                {"port_id": "receptor-in", "node_id": "receptor", "side": "left"},
                {"port_id": "pathway-in", "node_id": "pathway", "side": "left"},
                {"port_id": "pathway-out", "node_id": "pathway", "side": "right"},
            ],
            "typed_edges": [
                {
                    "edge_id": "activation",
                    "source_port": "receptor-out",
                    "target_port": "pathway-in",
                    "direction": "forward",
                    "semantic_type": "activation",
                },
                {
                    "edge_id": "feedback",
                    "source_port": "pathway-out",
                    "target_port": "receptor-in",
                    "direction": "forward",
                    "semantic_type": "feedback",
                },
            ],
            "groups": [],
            "labels": [],
            "constraints": [],
        },
    }


def test_figure_graph_preserves_cycles_and_cross_panel_edges():
    request = _request()
    graph = build_figure_graph(request, create_figure_plan(request))

    assert {node["node_id"] for node in graph["nodes"]} == {
        "receptor", "pathway",
    }
    assert [edge["edge_id"] for edge in graph["typed_edges"]] == [
        "activation", "feedback",
    ]

    solved = solve_figure_layout(graph, request["canvas"], {
        "receptor": [0.05, 0.2, 0.4, 0.6],
        "pathway": [0.55, 0.2, 0.4, 0.6],
    })

    assert len(solved["connectors"]) == 2
    assert solved["conflicts"] == []
    assert solved["nodes"][0]["bbox"] == [0.05, 0.2, 0.4, 0.6]
    assert solved["nodes"][1]["bbox"] == [0.55, 0.2, 0.4, 0.6]
    svg = render_figure_blueprint(solved)
    assert 'data-node-id="receptor"' in svg
    assert 'data-edge-id="feedback"' in svg


def test_figure_graph_rejects_edge_with_unknown_port():
    request = _request()
    request["figure_graph"]["typed_edges"][0]["target_port"] = "missing"

    with pytest.raises(ValueError, match="unknown target port"):
        build_figure_graph(request, create_figure_plan(request))


def test_layout_solver_applies_alignment_spacing_groups_and_exclusion_zones():
    request = _request()
    request["figure_graph"]["groups"] = [{
        "group_id": "mechanism", "node_ids": ["receptor", "pathway"],
        "padding": 0.01,
    }]
    request["figure_graph"]["constraints"] = [
        {"kind": "align", "axis": "y", "node_ids": ["receptor", "pathway"]},
        {"kind": "minimum_spacing", "axis": "x",
         "node_ids": ["receptor", "pathway"], "gap": 0.1},
        {"kind": "exclude", "bbox": [0.0, 0.0, 0.1, 0.1],
         "node_ids": ["receptor"]},
    ]
    graph = build_figure_graph(request, create_figure_plan(request))

    solved = solve_figure_layout(graph, request["canvas"], {
        "receptor": [0.05, 0.2, 0.2, 0.3],
        "pathway": [0.55, 0.4, 0.2, 0.3],
    })

    by_id = {item["node_id"]: item for item in solved["nodes"]}
    assert by_id["pathway"]["bbox"][0] == 0.35
    assert by_id["pathway"]["bbox"][1] == 0.2
    assert solved["groups"][0]["bbox"] == [0.04, 0.19, 0.52, 0.32]
    assert solved["connectors"][0]["points"][1][0] == (
        solved["connectors"][0]["points"][2][0]
    )
