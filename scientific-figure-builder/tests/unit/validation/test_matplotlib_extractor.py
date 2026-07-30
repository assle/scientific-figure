"""Unit tests for the matplotlib layout extractor (plan section 20.1)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from figure_tools.validation.extractors.matplotlib import extract_matplotlib_layout


def _figure_with_colorbar():
    fig, ax = plt.subplots(figsize=(4, 3))
    data = np.arange(100).reshape(10, 10)
    im = ax.imshow(data, aspect="auto")
    ax.set_title("Heat")
    ax.set_xlabel("X axis")
    ax.set_ylabel("Y axis")
    fig.colorbar(im, ax=ax, label="scale")
    fig.canvas.draw()
    return fig


def test_extract_captures_all_element_types():
    fig = _figure_with_colorbar()
    try:
        manifest = extract_matplotlib_layout(fig, "plot:test")
    finally:
        plt.close(fig)

    types = {e.element_type for e in manifest.elements}
    assert "title" in types
    assert "axis_label" in types
    assert "tick_label" in types
    assert "data_region" in types
    assert "colorbar" in types

    title = next(e for e in manifest.elements if e.element_type == "title")
    assert title.text == "Heat"
    assert title.font_size_pt is not None

    cb = next(e for e in manifest.elements if e.element_type == "colorbar")
    assert cb.bbox.area > 0


def test_extract_uses_top_left_origin_and_canvas_bounds():
    fig = _figure_with_colorbar()
    try:
        manifest = extract_matplotlib_layout(fig, "plot:test")
    finally:
        plt.close(fig)
    assert manifest.coordinate_system == "pixel_top_left"
    cw, ch = manifest.canvas_width_px, manifest.canvas_height_px
    assert cw > 0 and ch > 0
    # Every element bbox (allowing small matplotlib overflow) is near the canvas.
    tol = 32
    for e in manifest.elements:
        b = e.bbox
        assert -tol <= b.x1 and b.x2 <= cw + tol
        assert -tol <= b.y1 and b.y2 <= ch + tol


def test_extract_is_deterministic():
    figs = []
    manifests = []
    for _ in range(2):
        fig = _figure_with_colorbar()
        try:
            manifests.append(extract_matplotlib_layout(fig, "plot:test"))
        finally:
            plt.close(fig)
    assert manifests[0].to_dict() == manifests[1].to_dict()
