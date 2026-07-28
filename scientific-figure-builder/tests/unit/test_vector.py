"""SVG primitives and LaTeX-to-SVG tests."""

from __future__ import annotations

from figure_tools.vector.latex import latex_to_svg
from figure_tools.vector.primitives import SvgCanvas


def test_svg_canvas_renders_document() -> None:
    canvas = SvgCanvas(width=200, height=100)
    svg = canvas.to_string()
    assert svg.startswith("<svg")
    assert "</svg>" in svg
    assert 'width="200"' in svg
    assert 'height="100"' in svg


def test_svg_canvas_primitives_are_present() -> None:
    canvas = SvgCanvas(width=200, height=100)
    canvas.rect(10, 10, 50, 50, stroke="black", fill="none")
    canvas.line(0, 0, 10, 10, stroke="red")
    canvas.circle(100, 50, 5, fill="blue")
    canvas.text(20, 20, "hello", font_size=8)
    svg = canvas.to_string()
    assert "<rect" in svg
    assert "<line" in svg
    assert "<circle" in svg
    assert "<text" in svg
    assert "hello" in svg


def test_svg_arrow_has_marker() -> None:
    canvas = SvgCanvas(width=200, height=100)
    canvas.arrow(0, 0, 50, 50, stroke="black")
    svg = canvas.to_string()
    assert "<line" in svg
    assert "marker-end" in svg
    assert "<marker" in svg


def test_svg_path_primitive() -> None:
    canvas = SvgCanvas(width=200, height=100)
    canvas.path("M 0 0 L 10 10", stroke="green", fill="none")
    assert "<path" in canvas.to_string()


def test_latex_to_svg_returns_svg() -> None:
    svg = latex_to_svg(r"\alpha + \beta = \gamma")
    assert "<svg" in svg
    assert "</svg>" in svg
    assert len(svg) > 100


def test_latex_to_svg_is_deterministic() -> None:
    a = latex_to_svg(r"E = mc^2")
    b = latex_to_svg(r"E = mc^2")
    assert a == b


def test_latex_to_svg_rejects_invalid() -> None:
    import pytest

    with pytest.raises(Exception):
        latex_to_svg(r"\notacommand{")


def test_svg_canvas_is_deterministic() -> None:
    c1 = SvgCanvas(width=100, height=100)
    c1.rect(0, 0, 10, 10, stroke="black", fill="none")
    c2 = SvgCanvas(width=100, height=100)
    c2.rect(0, 0, 10, 10, stroke="black", fill="none")
    assert c1.to_string() == c2.to_string()
