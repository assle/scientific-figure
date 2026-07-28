"""Plot-spec loader and validator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from figure_tools.plotting.spec import PlotSpec, load_plot_spec

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def test_load_plot_spec_returns_typed_spec() -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    assert isinstance(spec, PlotSpec)
    assert spec.chart_type == "line"
    assert spec.recipe_version == "line-1.0"
    assert spec.source_data["path"] == "tests/fixtures/coupling.csv"
    assert spec.source_data["content_hash"].startswith("sha256:")


def test_load_plot_spec_rejects_invalid() -> None:
    bad = {
        "schema_version": "1.0",
        "chart_type": "line",
        # missing many required fields
    }
    with pytest.raises(Exception):
        load_plot_spec(bad)


def test_load_plot_spec_rejects_unknown_chart_type() -> None:
    bad = {
        "schema_version": "1.0",
        "chart_type": "violin",
        "recipe_version": "x",
        "source_data": {"path": "p", "content_hash": "sha256:x"},
        "column_mapping": {},
        "units": {},
        "series": [],
        "errors": [],
        "transformations": [],
        "filters": [],
        "axes": {"x": "x", "y": "y"},
        "scales": {},
        "ticks": {},
        "legends": [],
        "labels": {"title": "t", "x": "x", "y": "y"},
        "figure": {"dimensions": [1, 1], "style": "s"},
        "export": {"formats": ["png"], "dpi": 300},
        "validation_expectations": {},
    }
    with pytest.raises(Exception):
        load_plot_spec(bad)


def test_content_hash_matches_fixture_file() -> None:
    import hashlib

    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    raw = (FIXTURES / "coupling.csv").read_bytes()
    assert spec.source_data["content_hash"] == "sha256:" + hashlib.sha256(raw).hexdigest()
