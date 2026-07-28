"""Optional PPTX exporter tests."""

from __future__ import annotations

import filecmp
import zipfile
from pathlib import Path

from figure_tools.export.exporters import export_pptx
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec

ROOT = Path(__file__).resolve().parents[2]


def _make_plot(tmp_path: Path) -> Path:
    spec = load_plot_spec(ROOT / "tests" / "fixtures" / "plot_spec_line.json")
    d = tmp_path / "src"; d.mkdir()
    out = render_plot(spec, output_dir=d, base_dir=ROOT)
    return Path(out["files"]["png"])


def test_export_pptx_produces_valid_file(tmp_path: Path) -> None:
    img = _make_plot(tmp_path)
    out = tmp_path / "figure.pptx"
    export_pptx(
        [{"path": str(img), "bbox": [0.0, 0.0, 1.0, 1.0], "z_order": 1}],
        out, canvas_mm=(180, 90), title="Coupling efficiency",
    )
    assert out.is_file() and out.stat().st_size > 0
    assert zipfile.is_zipfile(out)


def test_export_pptx_is_reproducible(tmp_path: Path) -> None:
    img = _make_plot(tmp_path)
    placements = [{"path": str(img), "bbox": [0.0, 0.0, 1.0, 1.0], "z_order": 1}]
    a = tmp_path / "a.pptx"; b = tmp_path / "b.pptx"
    export_pptx(placements, a, canvas_mm=(180, 90))
    export_pptx(placements, b, canvas_mm=(180, 90))
    assert filecmp.cmp(a, b, shallow=False), "pptx not byte-identical across runs"
