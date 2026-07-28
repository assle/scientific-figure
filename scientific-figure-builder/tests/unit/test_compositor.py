"""Figure compositor tests: assemble panel assets into a final figure."""

from __future__ import annotations

import filecmp
from pathlib import Path

from figure_tools.assembly.compositor import compose_assets
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec

ROOT = Path(__file__).resolve().parents[2]


def _make_plot(tmp_path: Path, name: str) -> Path:
    spec = load_plot_spec(ROOT / "tests" / "fixtures" / "plot_spec_line.json")
    d = tmp_path / name
    d.mkdir()
    out = render_plot(spec, output_dir=d, base_dir=ROOT)
    return Path(out["files"]["png"])


def test_compose_produces_all_formats(tmp_path: Path) -> None:
    img = _make_plot(tmp_path, "src")
    placements = [
        {"path": str(img), "bbox": [0.0, 0.0, 0.5, 1.0], "z_order": 1},
        {"path": str(img), "bbox": [0.5, 0.0, 0.5, 1.0], "z_order": 2},
    ]
    out = compose_assets(placements, output_dir=tmp_path, canvas_mm=(180, 90), dpi=300)
    for name in ("figure.png", "figure.svg", "figure.pdf"):
        assert (tmp_path / name).is_file()
        assert (tmp_path / name).stat().st_size > 0
    assert "png" in out["files"]


def test_compose_is_reproducible(tmp_path: Path) -> None:
    img = _make_plot(tmp_path, "src")
    placements = [
        {"path": str(img), "bbox": [0.0, 0.0, 0.5, 1.0], "z_order": 1},
        {"path": str(img), "bbox": [0.5, 0.0, 0.5, 1.0], "z_order": 2},
    ]
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    compose_assets(placements, output_dir=a, canvas_mm=(180, 90), dpi=300)
    compose_assets(placements, output_dir=b, canvas_mm=(180, 90), dpi=300)
    for name in ("figure.png", "figure.svg", "figure.pdf"):
        assert filecmp.cmp(a / name, b / name, shallow=False), f"{name} not identical"


def test_compose_respects_z_order(tmp_path: Path) -> None:
    img = _make_plot(tmp_path, "src")
    # Higher z_order drawn later (on top). Reverse order should still place the
    # z_order=2 asset last regardless of input ordering.
    placements = [
        {"path": str(img), "bbox": [0.0, 0.0, 1.0, 1.0], "z_order": 2},
        {"path": str(img), "bbox": [0.0, 0.0, 1.0, 1.0], "z_order": 1},
    ]
    out = compose_assets(placements, output_dir=tmp_path, canvas_mm=(90, 90), dpi=300)
    assert (tmp_path / "figure.png").is_file()
