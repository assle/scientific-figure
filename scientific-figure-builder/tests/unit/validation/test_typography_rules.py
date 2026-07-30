"""Unit tests for the typography rule (plan section 20.1)."""

from __future__ import annotations

from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.rules.typography import minimum_font_size

TH = {"minimum_font_size_pt": 7, "critical_font_size_pt": 6,
      "font_size_tolerance_pt": 1}


def _manifest(elements, cw=1000, ch=1000):
    return LayoutManifest("1.0", "t", "pixel_top_left", cw, ch, elements)


def _el(eid, etype, bbox, fs=None):
    return LayoutElement(eid, etype, PixelBBox.from_list(bbox), font_size_pt=fs)


def test_pass_when_all_sizes_ok():
    m = _manifest([_el("a", "tick_label", [0, 0, 50, 20], fs=8.0),
                   _el("b", "tick_label", [0, 30, 50, 50], fs=8.0)])
    assert all(c["status"] == "pass" for c in minimum_font_size(m, TH))


def test_error_below_critical():
    m = _manifest([_el("a", "text", [0, 0, 50, 20], fs=5.5)])
    fails = [c for c in minimum_font_size(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "error"
    assert fails[0]["element_ids"] == ["a"]


def test_warning_below_minimum():
    m = _manifest([_el("a", "text", [0, 0, 50, 20], fs=6.5)])
    fails = [c for c in minimum_font_size(m, TH) if c["status"] == "fail"]
    assert fails and fails[0]["level"] == "warning"


def test_warning_for_inconsistent_same_type_sizes():
    m = _manifest([_el("a", "tick_label", [0, 0, 50, 20], fs=8.0),
                   _el("b", "tick_label", [0, 30, 50, 50], fs=10.0)])
    fails = [c for c in minimum_font_size(m, TH) if c["status"] == "fail"]
    assert any("vary" in c["detail"] for c in fails)
