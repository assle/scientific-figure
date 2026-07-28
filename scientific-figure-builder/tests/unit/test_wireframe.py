"""Layout wireframe generator tests (no-cost SVG, plan section 4 step 7)."""

from __future__ import annotations

import json
from pathlib import Path

from figure_tools.vector.wireframe import generate_wireframe

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def test_wireframe_returns_svg() -> None:
    plan = json.loads((FIXTURES / "figure_plan.json").read_text(encoding="utf-8"))
    svg = generate_wireframe(plan)
    assert svg.startswith("<svg")
    assert "</svg>" in svg


def test_wireframe_has_one_rect_per_panel() -> None:
    plan = json.loads((FIXTURES / "figure_plan.json").read_text(encoding="utf-8"))
    svg = generate_wireframe(plan)
    # two panels in the fixture
    assert svg.count("<rect") == len(plan["panels"])


def test_wireframe_includes_panel_labels() -> None:
    plan = json.loads((FIXTURES / "figure_plan.json").read_text(encoding="utf-8"))
    svg = generate_wireframe(plan)
    for panel in plan["panels"]:
        assert panel["panel_id"] in svg


def test_wireframe_is_deterministic() -> None:
    plan = json.loads((FIXTURES / "figure_plan.json").read_text(encoding="utf-8"))
    assert generate_wireframe(plan) == generate_wireframe(plan)
