"""Exporter tests: deterministic output and PowerPoint-ready SVG."""

from __future__ import annotations

import filecmp
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from figure_tools.export.exporters import export_svg
from figure_tools.vector.svg_normalize import normalize_ppt_svg_bytes


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


def test_export_svg_ppt_declares_office_font_family(tmp_path: Path) -> None:
    fig = _text_figure()
    try:
        path = export_svg(fig, tmp_path / "ppt.svg", export_target="ppt")
        svg = path.read_text(encoding="utf-8")
        assert "<text" in svg
        assert "Arial, SimSun, sans-serif" in svg
    finally:
        plt.close(fig)


def test_ppt_normalize_defaults_missing_font_size() -> None:
    svg = normalize_ppt_svg_bytes(
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<text x="1" y="2">hi</text></svg>'
    ).decode("utf-8")
    assert 'font-family="Arial, SimSun, sans-serif"' in svg
    assert 'font-size="7.5"' in svg


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
