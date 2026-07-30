"""Unit tests for clipping and asset-bounds rules (plan section 20.1)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.rules.clipping import asset_bounds, text_clipping

TH = {"minimum_overlap_pixels": 2, "panel_padding_pixels": 2}


def _manifest(elements, cw=1000, ch=1000):
    return LayoutManifest("1.0", "t", "pixel_top_left", cw, ch, elements)


def _el(eid, etype, bbox, **kw):
    return LayoutElement(eid, etype, PixelBBox.from_list(bbox), **kw)


def test_text_clipping_pass_inside_panel():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("t", "text", [10, 10, 100, 40], panel_id="a"),
    ])
    checks = text_clipping(m, TH)
    assert all(c["status"] == "pass" for c in checks)


def test_text_clipping_error_when_beyond_canvas():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("t", "text", [-20, 10, 100, 40], panel_id="a"),
    ])
    fails = [c for c in text_clipping(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "error"
    assert fails[0]["element_ids"] == ["t"]


def test_text_clipping_warning_when_beyond_panel():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("t", "text", [490, 10, 600, 40], panel_id="a"),  # exceeds panel x
    ])
    fails = [c for c in text_clipping(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "warning"


def test_panel_label_only_checked_against_canvas():
    # Panel labels may sit in the panel padding; only canvas clipping matters.
    m = _manifest([
        _el("panel_a", "panel", [100, 100, 500, 1000], panel_id="a"),
        _el("lab", "panel_label", [80, 80, 130, 110], panel_id="a"),  # in padding
    ])
    checks = text_clipping(m, TH)
    assert all(c["status"] == "pass" for c in checks)


def test_asset_bounds_pass():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("d", "data_region", [10, 10, 490, 990], panel_id="a"),
        _el("l", "legend", [20, 20, 200, 80], panel_id="a"),
    ])
    assert all(c["status"] == "pass" for c in asset_bounds(m, TH))


def test_asset_bounds_error_beyond_canvas():
    m = _manifest([
        _el("c", "colorbar", [990, 0, 1100, 1000], panel_id="a"),
    ])
    fails = [c for c in asset_bounds(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "error"
