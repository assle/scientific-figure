"""Recipe coverage: each v1 recipe renders reproducible outputs."""

from __future__ import annotations

import filecmp
from pathlib import Path

from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec

ROOT = Path(__file__).resolve().parents[2]


def _base_spec(chart_type: str) -> dict:
    return {
        "schema_version": "1.0",
        "chart_type": chart_type,
        "recipe_version": f"{chart_type}-1.0",
        "source_data": {
            "path": "tests/fixtures/coupling.csv",
            "content_hash": "sha256:ef43ca675194c4ab9cb4dbcd57c280042bb177c63601b92cec838e0cd7841fcd",
        },
        "column_mapping": {"x": "offset_um", "y": "efficiency"},
        "units": {"offset_um": "um", "efficiency": "percent"},
        "series": [
            {"series_id": "s1", "x": "offset_um", "y": "efficiency", "label": "s1"},
            {"series_id": "s2", "x": "offset_um", "y": "efficiency_std", "label": "s2"},
        ],
        "errors": [{"series_id": "s1", "y_err": "efficiency_std"}],
        "transformations": [],
        "filters": [],
        "axes": {"x": "offset_um", "y": "efficiency"},
        "scales": {"x": "linear", "y": "linear"},
        "ticks": {"x": [-2, -1, 0, 1, 2]},
        "legends": [{"loc": "best"}],
        "labels": {"title": "t", "x": "x", "y": "y"},
        "figure": {"dimensions": [3.5, 2.6], "style": "publication"},
        "export": {"formats": ["png", "svg", "pdf"], "dpi": 300},
        "validation_expectations": {"min_samples": 1},
    }


CHART_TYPES = ["scatter", "bar", "heatmap", "error_bar", "multipanel"]


def test_line_recipe_from_fixture_validates(tmp_path: Path) -> None:
    spec = load_plot_spec(ROOT / "tests" / "fixtures" / "plot_spec_line.json")
    out = render_plot(spec, output_dir=tmp_path, base_dir=ROOT)
    assert "png" in out["files"]


def test_each_recipe_renders_all_formats(tmp_path: Path) -> None:
    for ct in CHART_TYPES:
        d = tmp_path / ct
        d.mkdir()
        spec = load_plot_spec(_base_spec(ct))
        out = render_plot(spec, output_dir=d, base_dir=ROOT)
        for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv"):
            assert (d / name).is_file() and (d / name).stat().st_size > 0


def test_each_recipe_is_reproducible(tmp_path: Path) -> None:
    for ct in CHART_TYPES:
        a = tmp_path / f"{ct}_a"
        b = tmp_path / f"{ct}_b"
        a.mkdir(); b.mkdir()
        spec = load_plot_spec(_base_spec(ct))
        render_plot(spec, output_dir=a, base_dir=ROOT)
        render_plot(spec, output_dir=b, base_dir=ROOT)
        for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv"):
            assert filecmp.cmp(a / name, b / name, shallow=False), f"{ct}/{name} not identical"
