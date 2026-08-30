from __future__ import annotations

import copy
import json
from pathlib import Path

from figure_tools.validation.graph_structure import (
    build_structure_questions,
    validate_graph_structure,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_graph_structure_requires_every_node_and_directed_edge():
    graph = _load("figure_graph.json")
    graph["ports"].append({
        "port_id": "receptor-in", "node_id": "receptor", "side": "left",
    })
    graph["typed_edges"].append({
        "edge_id": "feedback",
        "source_port": "receptor-out",
        "target_port": "receptor-in",
        "direction": "forward",
        "semantic_type": "feedback",
    })
    solved = _load("solved_layout.json")

    checks = validate_graph_structure(graph, solved)

    by_id = {item["check_id"]: item for item in checks}
    assert by_id["graph_node_recovery"]["status"] == "pass"
    assert by_id["graph_edge_recovery"]["status"] == "fail"
    assert by_id["graph_edge_recovery"]["level"] == "error"
    assert by_id["graph_edge_recovery"]["element_ids"] == ["feedback"]


def test_structure_questions_cover_four_reasoning_levels():
    questions = build_structure_questions(_load("figure_graph.json"))

    assert {item["level"] for item in questions} == {
        "component", "local_topology", "phase", "global_semantics",
    }
    assert all(item["critical"] is True for item in questions)


def test_group_recovery_checks_phase_membership_not_only_identity():
    graph = _load("figure_graph.json")
    graph["groups"] = [{"group_id": "phase-a", "node_ids": ["receptor"]}]
    observed = _load("solved_layout.json")
    observed["groups"] = [{"group_id": "phase-a", "node_ids": ["other"]}]

    checks = validate_graph_structure(graph, observed)

    group_check = next(
        item for item in checks if item["check_id"] == "graph_group_recovery"
    )
    assert group_check["status"] == "fail"
    assert group_check["element_ids"] == ["phase-a"]
