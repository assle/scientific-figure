"""Optional PPTX exporter tests."""

from __future__ import annotations

import filecmp
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from figure_tools.export.exporters import export_pptx, export_svg
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


def _text_figure():
    fig, ax = plt.subplots(figsize=(3, 2))
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("X label")
    ax.set_ylabel("Y label")
    ax.set_title("Title")
    return fig


def test_export_svg_general_keeps_text_as_paths(tmp_path: Path) -> None:
    fig = _text_figure()
    try:
        path = export_svg(fig, tmp_path / "general.svg", export_target="general")
        svg = path.read_text(encoding="utf-8")
        assert "<use" in svg
        assert "<text" not in svg
    finally:
        plt.close(fig)


def test_export_svg_ppt_uses_editable_text(tmp_path: Path) -> None:
    fig = _text_figure()
    try:
        path = export_svg(fig, tmp_path / "ppt.svg", export_target="ppt")
        svg = path.read_text(encoding="utf-8")
        assert "<text" in svg
        assert "text-anchor" in svg
    finally:
        plt.close(fig)


def test_export_svg_ppt_is_deterministic(tmp_path: Path) -> None:
    fig1 = _text_figure()
    fig2 = _text_figure()
    try:
        a = export_svg(fig1, tmp_path / "a.svg", export_target="ppt")
        b = export_svg(fig2, tmp_path / "b.svg", export_target="ppt")
        assert filecmp.cmp(a, b, shallow=False)
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_export_svg_rejects_unknown_target(tmp_path: Path) -> None:
    fig = _text_figure()
    try:
        with pytest.raises(ValueError):
            export_svg(fig, tmp_path / "bad.svg", export_target="unknown")
    finally:
        plt.close(fig)
