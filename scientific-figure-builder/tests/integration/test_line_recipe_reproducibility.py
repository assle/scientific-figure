"""Phase 2 exit-criteria integration test: CSV -> reproducible publication plot.

Verifies (plan section 15, Phase 2):
- A CSV-only example produces reproducible outputs.
- Repeated execution produces identical local artifacts.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


def test_csv_line_plot_produces_all_formats(tmp_path: Path) -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    out = render_plot(spec, output_dir=tmp_path, base_dir=ROOT)
    for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv"):
        assert (tmp_path / name).is_file(), f"missing output {name}"
    assert "data_used.csv" in out["files"]


def test_repeated_render_is_byte_identical(tmp_path: Path) -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    render_plot(spec, output_dir=dir_a, base_dir=ROOT)
    render_plot(spec, output_dir=dir_b, base_dir=ROOT)
    for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv"):
        assert filecmp.cmp(dir_a / name, dir_b / name, shallow=False), (
            f"{name} not byte-identical across runs"
        )


def test_rendered_outputs_are_nonempty(tmp_path: Path) -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    render_plot(spec, output_dir=tmp_path, base_dir=ROOT)
    for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv"):
        assert (tmp_path / name).stat().st_size > 0


def test_data_used_csv_matches_source(tmp_path: Path) -> None:
    import pandas as pd

    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    render_plot(spec, output_dir=tmp_path, base_dir=ROOT)
    used = pd.read_csv(tmp_path / "data_used.csv")
    src = pd.read_csv(FIXTURES / "coupling.csv")
    assert list(used["offset_um"]) == list(src["offset_um"])
    assert list(used["efficiency"]) == list(src["efficiency"])
