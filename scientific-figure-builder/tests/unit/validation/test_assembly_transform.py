"""Unit tests for assembly coordinate mapping (plan section 20.1)."""

from __future__ import annotations

from figure_tools.validation.extractors.assembly import (
    map_bbox,
    transform_source_manifest,
)
from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox


def _src(elements, sw=1000, sh=800):
    return LayoutManifest("1.0", "plot:x", "pixel_top_left", sw, sh, elements)


def test_map_bbox_uniform_placement():
    # source 1000x800 placed at [0,0,0.5,1.0] on a 2000x800 canvas.
    out = map_bbox(PixelBBox(100, 100, 200, 200), [0, 0, 0.5, 1.0], 2000, 800, 1000, 800)
    # scale_x = 0.5*2000/1000 = 1.0 ; scale_y = 1.0*800/800 = 1.0
    assert out.as_list() == [100, 100, 200, 200]


def test_map_bbox_nonuniform_aspect_auto():
    # source 1000x800 placed at [0,0,0.5,1.0] on a 2000x1600 canvas (x and y
    # scale differently under aspect="auto").
    out = map_bbox(PixelBBox(100, 100, 200, 200), [0, 0, 0.5, 1.0], 2000, 1600, 1000, 800)
    # scale_x = 0.5*2000/1000 = 1.0 ; scale_y = 1.0*1600/800 = 2.0
    assert out.as_list() == [100, 200, 200, 400]


def test_map_bbox_offset_placement():
    # source 1000x800 placed at [0.5,0,0.5,1.0] (right half) on 2000x800.
    out = map_bbox(PixelBBox(100, 100, 200, 200), [0.5, 0, 0.5, 1.0], 2000, 800, 1000, 800)
    # px*cw = 1000 ; scale_x = 0.5*2000/1000 = 1.0
    assert out.as_list() == [1100, 100, 1200, 200]


def test_transform_source_manifest_preserves_metadata_and_panel():
    src = _src([LayoutElement("title_0", "title", PixelBBox(10, 10, 100, 40),
                              text="T", font_size_pt=12.0, source="matplotlib")])
    placement = {"asset_id": "curve", "bbox": [0.0, 0.0, 0.5, 1.0],
                 "z_order": 1, "panel_id": "a"}
    out = transform_source_manifest(src, placement, 2000, 800, "a")
    assert len(out) == 1
    el = out[0]
    assert el.element_id == "curve:title_0"
    assert el.element_type == "title"
    assert el.text == "T"
    assert el.font_size_pt == 12.0
    assert el.panel_id == "a"
    assert el.source == "assembly"
    assert el.z_order == 1
