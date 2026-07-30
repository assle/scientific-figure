"""Integration: render_plot emits a layout manifest (plan section 20.2)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.validation.models import read_layout_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_render_plot_emits_layout_manifest(tmp_path: Path) -> None:
    spec = load_plot_spec(ROOT / "tests" / "fixtures" / "plot_spec_line.json")
    out = render_plot(spec, output_dir=tmp_path, base_dir=ROOT)

    # All expected files exist, including the new manifest.
    for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv",
                 "layout_manifest.json"):
        assert (tmp_path / name).is_file(), f"missing {name}"
    assert "layout_manifest.json" in out["files"]

    manifest = read_layout_manifest(tmp_path / "layout_manifest.json")

    # Schema conformance.
    schema = json.loads(schema_path("layout-manifest.schema.json").read_text("utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(manifest.to_dict()))

    # Top-left origin convention.
    assert manifest.coordinate_system == "pixel_top_left"
    assert manifest.canvas_width_px > 0
    assert manifest.canvas_height_px > 0

    types = {e.element_type for e in manifest.elements}
    # At least axis label, tick label, and a data region are present.
    assert "axis_label" in types
    assert "tick_label" in types
    assert "data_region" in types
    # Title text is captured.
    titles = [e for e in manifest.elements if e.element_type == "title"]
    assert titles and titles[0].text == "Coupling efficiency"

    # Every bbox lies within the canvas (small tolerance: matplotlib text may
    # overflow the figure edge by a few pixels -- plan risk 1).
    tol = 16
    for el in manifest.elements:
        b = el.bbox
        assert -tol <= b.x1 <= b.x2 <= manifest.canvas_width_px + tol
        assert -tol <= b.y1 <= b.y2 <= manifest.canvas_height_px + tol


def test_render_plot_manifest_is_deterministic(tmp_path: Path) -> None:
    spec = load_plot_spec(ROOT / "tests" / "fixtures" / "plot_spec_line.json")
    a = render_plot(spec, output_dir=tmp_path / "a", base_dir=ROOT)
    b = render_plot(spec, output_dir=tmp_path / "b", base_dir=ROOT)
    ma = read_layout_manifest(a["files"]["layout_manifest.json"])
    mb = read_layout_manifest(b["files"]["layout_manifest.json"])
    assert ma.to_dict() == mb.to_dict()
