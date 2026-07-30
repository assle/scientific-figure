"""Unit tests for panel-label rules (plan section 20.1)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.rules.panel_labels import (
    panel_label_collision,
    panel_label_consistency,
)

TH = {"minimum_overlap_pixels": 2, "font_size_tolerance_pt": 1}


def _manifest(elements, cw=1000, ch=1000):
    return LayoutManifest("1.0", "t", "pixel_top_left", cw, ch, elements)


def _el(eid, etype, bbox, **kw):
    return LayoutElement(eid, etype, PixelBBox.from_list(bbox), **kw)


def test_collision_detected_with_tick_label():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("lab", "panel_label", [10, 10, 60, 50], panel_id="a", text="(a)"),
        _el("tk", "tick_label", [30, 20, 80, 60], panel_id="a", text="100"),
    ])
    fails = [c for c in panel_label_collision(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "error"
    assert "lab" in fails[0]["element_ids"] and "tk" in fails[0]["element_ids"]


def test_collision_pass_when_no_overlap():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("lab", "panel_label", [10, 10, 60, 50], panel_id="a", text="(a)"),
        _el("tk", "tick_label", [300, 500, 360, 540], panel_id="a", text="100"),
    ])
    assert all(c["status"] == "pass" for c in panel_label_collision(m, TH))


def test_consistency_pass_for_clean_panels():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("panel_b", "panel", [500, 0, 1000, 1000], panel_id="b"),
        _el("lab_a", "panel_label", [10, 10, 60, 50], panel_id="a",
            text="(a)", font_size_pt=9.0),
        _el("lab_b", "panel_label", [510, 10, 560, 50], panel_id="b",
            text="(b)", font_size_pt=9.0),
    ])
    assert all(c["status"] == "pass" for c in panel_label_consistency(m, TH))


def test_consistency_flags_missing_label():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("panel_b", "panel", [500, 0, 1000, 1000], panel_id="b"),
        _el("lab_a", "panel_label", [10, 10, 60, 50], panel_id="a", text="(a)"),
    ])
    fails = [c for c in panel_label_consistency(m, TH) if c["status"] == "fail"]
    assert any("panel b" in c["detail"] for c in fails)


def test_consistency_flags_duplicate_labels():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("panel_b", "panel", [500, 0, 1000, 1000], panel_id="b"),
        _el("lab_a", "panel_label", [10, 10, 60, 50], panel_id="a", text="(a)"),
        _el("lab_b", "panel_label", [510, 10, 560, 50], panel_id="b", text="(a)"),
    ])
    fails = [c for c in panel_label_consistency(m, TH) if c["status"] == "fail"]
    assert any("duplicate" in c["detail"] for c in fails)


def test_consistency_flags_bad_format_and_font_variation():
    m = _manifest([
        _el("panel_a", "panel", [0, 0, 500, 1000], panel_id="a"),
        _el("panel_b", "panel", [500, 0, 1000, 1000], panel_id="b"),
        _el("lab_a", "panel_label", [10, 10, 60, 50], panel_id="a",
            text="A.", font_size_pt=9.0),
        _el("lab_b", "panel_label", [510, 10, 560, 50], panel_id="b",
            text="(b)", font_size_pt=12.0),
    ])
    fails = [c for c in panel_label_consistency(m, TH) if c["status"] == "fail"]
    detail = " ".join(c["detail"] for c in fails)
    assert "format" in detail or "(a)" in detail
    assert any("font size" in c["detail"] for c in fails)
