"""Unit tests for the overlap and geometry rules (plan section 20.1)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.rules.geometry import (
    contains,
    intersection_area,
    intersection_bbox,
)
from figure_tools.validation.rules.overlap import text_text_overlap

TH = {"minimum_overlap_pixels": 2, "overlap_warning_ratio": 0.01,
      "overlap_error_ratio": 0.03}


def _manifest(elements, cw=1000, ch=1000):
    return LayoutManifest("1.0", "t", "pixel_top_left", cw, ch, elements)


def _el(eid, etype, bbox, **kw):
    return LayoutElement(eid, etype, PixelBBox.from_list(bbox), **kw)


def test_intersection_no_overlap():
    assert intersection_bbox(PixelBBox(0, 0, 10, 10), PixelBBox(20, 20, 30, 30)) is None
    assert intersection_area(PixelBBox(0, 0, 10, 10), PixelBBox(20, 20, 30, 30)) == 0.0


def test_intersection_edge_touch_is_none():
    # Touching edges do not count as overlap (width/height == 0).
    assert intersection_bbox(PixelBBox(0, 0, 10, 10), PixelBBox(10, 0, 20, 10)) is None


def test_intersection_small_and_large():
    small = intersection_area(PixelBBox(0, 0, 10, 10), PixelBBox(8, 8, 20, 20))
    assert small == 4.0  # 2x2
    full = intersection_bbox(PixelBBox(0, 0, 10, 10), PixelBBox(2, 2, 8, 8))
    assert full is not None and full.area == 36.0


def test_contains_with_padding():
    outer = PixelBBox(0, 0, 100, 100)
    assert contains(outer, PixelBBox(5, 5, 95, 95))
    assert contains(outer, PixelBBox(-2, 0, 100, 100), padding=2)
    assert not contains(outer, PixelBBox(-3, 0, 100, 100), padding=2)


def test_overlap_pass_when_no_overlap():
    m = _manifest([
        _el("a", "text", [0, 0, 50, 50]),
        _el("b", "text", [60, 60, 100, 100]),
    ])
    checks = text_text_overlap(m, TH)
    assert len(checks) == 1 and checks[0]["status"] == "pass"


def test_overlap_warning_for_small_ratio():
    # 3x3 overlap over a 100x100 box -> 9/10000 = 0.09% -> below 1% -> pass.
    # Use a slightly larger overlap to land in 1-3% warning band.
    m = _manifest([
        _el("a", "text", [0, 0, 100, 100]),
        _el("b", "text", [97, 97, 120, 120]),  # 3x3=9 of min area 9*9=81? -> compute
    ])
    # min area = (120-97)*(120-97)=529; overlap=3*3=9 -> 1.7% -> warning
    fails = [c for c in text_text_overlap(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "warning"


def test_overlap_error_for_large_ratio():
    m = _manifest([
        _el("a", "text", [0, 0, 100, 100]),
        _el("b", "text", [0, 0, 50, 50]),  # 50% of smaller -> error
    ])
    fails = [c for c in text_text_overlap(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "error"
    assert "element_ids" in fails[0] and "bbox" in fails[0]
    assert fails[0]["method"] == "geometry"


def test_overlap_skips_panel_label_pairs():
    # Panel-label collisions are owned by the dedicated rule.
    m = _manifest([
        _el("a", "panel_label", [0, 0, 50, 50]),
        _el("b", "tick_label", [0, 0, 50, 50]),
    ])
    checks = text_text_overlap(m, TH)
    assert all(c["status"] == "pass" for c in checks)


def test_overlap_zero_area_ignored():
    m = _manifest([
        _el("a", "text", [10, 10, 10, 10]),  # zero area
        _el("b", "text", [10, 10, 20, 20]),
    ])
    checks = text_text_overlap(m, TH)
    assert all(c["status"] == "pass" for c in checks)
