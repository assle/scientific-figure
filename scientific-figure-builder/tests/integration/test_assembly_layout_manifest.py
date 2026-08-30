"""Integration: compose_assets emits an assembly layout manifest (plan 20.2)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.assembly.compositor import compose_assets
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.validation.models import read_layout_manifest

ROOT = Path(__file__).resolve().parents[2]


def _make_plot(tmp_path: Path, name: str) -> tuple[Path, Path]:
    spec = load_plot_spec(ROOT / "tests" / "fixtures" / "plot_spec_line.json")
    d = tmp_path / name
    out = render_plot(spec, output_dir=d, base_dir=ROOT)
    return Path(out["files"]["png"]), Path(out["files"]["layout_manifest.json"])


def test_assembly_manifest_maps_source_elements_and_labels(tmp_path: Path) -> None:
    png_a, man_a = _make_plot(tmp_path, "a")
    png_b, man_b = _make_plot(tmp_path, "b")
    placements = [
        {"asset_id": "curve", "path": str(png_a), "bbox": [0.0, 0.0, 0.5, 1.0],
         "panel_id": "a", "z_order": 1, "layout_manifest": str(man_a)},
        {"asset_id": "curve2", "path": str(png_b), "bbox": [0.5, 0.0, 0.5, 1.0],
         "panel_id": "b", "z_order": 2, "layout_manifest": str(man_b)},
    ]
    text_placements = [
        {"x": 0.02, "y": 0.02, "text": "(a) Coupling", "font_size": 9,
         "element_id": "label-a", "kind": "label", "panel_id": "a"},
        {"x": 0.52, "y": 0.02, "text": "(b) Coupling", "font_size": 9,
         "element_id": "label-b", "kind": "label", "panel_id": "b"},
    ]
    source_layouts = {"curve": str(man_a), "curve2": str(man_b)}

    out = compose_assets(placements, output_dir=tmp_path / "out", canvas_mm=(180, 90),
                         dpi=300, text_placements=text_placements,
                         source_layouts=source_layouts,
                         connectors=[{
                             "edge_id": "flow",
                             "source_port": "curve-out",
                             "target_port": "curve2-in",
                             "source": [0.45, 0.5],
                             "target": [0.55, 0.5],
                             "direction": "forward",
                             "semantic_type": "transfer",
                         }])

    assert "layout_manifest" in out
    manifest = read_layout_manifest(out["layout_manifest"])

    schema = json.loads(schema_path("layout-manifest.schema.json").read_text("utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(manifest.to_dict()))

    types = {e.element_type for e in manifest.elements}
    # Source elements were projected (axis labels from the plots).
    assert "axis_label" in types
    # Composed panel labels were extracted.
    labels = [e for e in manifest.elements if e.element_type == "panel_label"]
    assert len(labels) == 2
    label_ids = {e.element_id for e in labels}
    assert label_ids == {"label-a", "label-b"}

    # Panel label (a) sits in the left half; (b) in the right half.
    cw = manifest.canvas_width_px
    a_label = next(e for e in labels if e.element_id == "label-a")
    b_label = next(e for e in labels if e.element_id == "label-b")
    assert a_label.bbox.x2 <= cw / 2
    assert b_label.bbox.x1 >= cw / 2

    connector = next(
        element for element in manifest.elements
        if element.element_type == "connector"
    )
    assert connector.element_id == "edge:flow"
    assert connector.metadata["source_port"] == "curve-out"
    assert connector.metadata["target_port"] == "curve2-in"

    # A source axis label from plot (a) maps into the left half of the canvas.
    a_axis = next(e for e in manifest.elements
                  if e.element_type == "axis_label" and e.element_id.startswith("curve:"))
    assert a_axis.bbox.x2 <= cw / 2 + 1


def test_assembly_without_source_layouts_still_records_text(tmp_path: Path) -> None:
    png_a, _ = _make_plot(tmp_path, "a")
    placements = [
        {"asset_id": "curve", "path": str(png_a), "bbox": [0.0, 0.0, 1.0, 1.0],
         "panel_id": "a", "z_order": 1},
    ]
    text_placements = [
        {"x": 0.02, "y": 0.02, "text": "(a)", "font_size": 9,
         "element_id": "label-a", "kind": "label", "panel_id": "a"},
    ]
    out = compose_assets(placements, output_dir=tmp_path / "out", canvas_mm=(90, 90),
                         dpi=300, text_placements=text_placements)
    manifest = read_layout_manifest(out["layout_manifest"])
    labels = [e for e in manifest.elements if e.element_type == "panel_label"]
    assert len(labels) == 1
    assert labels[0].text == "(a)"
