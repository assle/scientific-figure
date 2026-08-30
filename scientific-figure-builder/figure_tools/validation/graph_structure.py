"""Deterministic structure checks and graph-derived critical questions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from figure_tools.validation.summary import make_check


def _f1(expected: set[str], observed: set[str]) -> dict[str, float]:
    matched = len(expected & observed)
    precision = matched / len(observed) if observed else (1.0 if not expected else 0.0)
    recall = matched / len(expected) if expected else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def validate_graph_structure(
    graph: Mapping[str, Any],
    observed_structure: Mapping[str, Any],
    *,
    conflicts: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    expected_nodes = {str(item["node_id"]) for item in graph.get("nodes", [])}
    observed_nodes = {
        str(item["node_id"]) for item in observed_structure.get("nodes", [])
    }
    missing_nodes = sorted(expected_nodes - observed_nodes)
    extra_nodes = sorted(observed_nodes - expected_nodes)
    node_check = make_check(
        "graph_node_recovery",
        "final",
        "error",
        "fail" if missing_nodes or extra_nodes else "pass",
        (
            f"missing nodes: {missing_nodes}; extra nodes: {extra_nodes}"
            if missing_nodes or extra_nodes
            else "all Figure Graph nodes recovered"
        ),
        element_ids=[*missing_nodes, *extra_nodes],
        metrics=_f1(expected_nodes, observed_nodes),
    )

    expected_edges = {
        str(item["edge_id"]): (
            str(item["source_port"]),
            str(item["target_port"]),
            str(item.get("direction") or "forward"),
        )
        for item in graph.get("typed_edges", [])
    }
    observed_edges = {
        str(item["edge_id"]): (
            str(item["source_port"]),
            str(item["target_port"]),
            str(item.get("direction") or "forward"),
        )
        for item in observed_structure.get("connectors", [])
    }
    incorrect_edges = sorted(
        edge_id
        for edge_id, expected in expected_edges.items()
        if observed_edges.get(edge_id) != expected
    )
    extra_edges = sorted(set(observed_edges) - set(expected_edges))
    recovered_edges = {
        edge_id for edge_id in expected_edges
        if observed_edges.get(edge_id) == expected_edges[edge_id]
    }
    edge_check = make_check(
        "graph_edge_recovery",
        "final",
        "error",
        "fail" if incorrect_edges or extra_edges else "pass",
        (
            f"missing or incorrect edges: {incorrect_edges}; extra edges: {extra_edges}"
            if incorrect_edges or extra_edges
            else "all directed Figure Graph edges recovered"
        ),
        element_ids=[*incorrect_edges, *extra_edges],
        metrics=_f1(set(expected_edges), recovered_edges | set(extra_edges)),
    )
    expected_groups = {
        str(item.get("group_id")) for item in graph.get("groups", [])
        if item.get("group_id")
    }
    observed_groups = {
        str(item.get("group_id")) for item in observed_structure.get("groups", [])
        if item.get("group_id")
    }
    missing_groups = sorted(expected_groups - observed_groups)
    extra_groups = sorted(observed_groups - expected_groups)
    group_check = make_check(
        "graph_group_recovery",
        "final",
        "error",
        "fail" if missing_groups or extra_groups else "pass",
        (
            f"missing groups: {missing_groups}; extra groups: {extra_groups}"
            if missing_groups or extra_groups
            else "all Figure Graph phases and groups recovered"
        ),
        element_ids=[*missing_groups, *extra_groups],
        metrics=_f1(expected_groups, observed_groups),
    )
    conflicts = list(conflicts or [])
    conflict_check = make_check(
        "figure_layout_conflicts",
        "final",
        "error",
        "fail" if conflicts else "pass",
        (
            "; ".join(str(item.get("detail") or item.get("kind")) for item in conflicts)
            if conflicts
            else "solved layout has no conflicts"
        ),
        element_ids=sorted({
            str(element_id)
            for item in conflicts
            for element_id in item.get("element_ids", [])
        }),
    )
    return [node_check, edge_check, group_check, conflict_check]


def build_structure_questions(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes = [str(item["node_id"]) for item in graph.get("nodes", [])]
    edges = [str(item["edge_id"]) for item in graph.get("typed_edges", [])]
    groups = [str(item.get("group_id") or "") for item in graph.get("groups", [])]
    return [
        {
            "question_id": "component-existence",
            "level": "component",
            "question": "Are all required components present?",
            "expected": nodes,
            "critical": True,
        },
        {
            "question_id": "local-topology",
            "level": "local_topology",
            "question": "Are all local directed relations connected correctly?",
            "expected": edges,
            "critical": True,
        },
        {
            "question_id": "phase-architecture",
            "level": "phase",
            "question": "Are the scientific phases or groups organized correctly?",
            "expected": [item for item in groups if item],
            "critical": True,
        },
        {
            "question_id": "global-semantics",
            "level": "global_semantics",
            "question": "Does the complete figure preserve the intended global mechanism?",
            "expected": {"nodes": nodes, "edges": edges},
            "critical": True,
        },
    ]


__all__ = ["build_structure_questions", "validate_graph_structure"]
