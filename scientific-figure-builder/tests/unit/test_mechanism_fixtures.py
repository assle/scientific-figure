import json
from pathlib import Path

from PIL import Image, ImageDraw

from figure_tools.figure_layout import solve_figure_layout
from figure_tools.imaging.edit_validation import evaluate_local_edit
from figure_tools.validation.formal_text import formal_text_checks
from figure_tools.validation.graph_structure import validate_graph_structure
from figure_tools.validation.image_checks import deterministic_image_checks
from figure_tools.validation.models import LayoutElement, LayoutManifest, PixelBBox
from figure_tools.validation.publication import (
    publication_accessibility_check,
    publication_profile_checks,
)
from figure_tools.validation.rules.ai_asset import unexpected_ai_text
from figure_tools.validation.rules.clipping import asset_bounds


CASES = Path(__file__).resolve().parents[1] / "fixtures" / "mechanism_cases"


def _graph():
    return {
        "schema_version": "1.0", "figure_id": "mechanism",
        "nodes": [
            {"node_id": "a", "node_type": "image_asset", "asset_id": "a",
             "panel_id": "p", "z_order": 1},
            {"node_id": "b", "node_type": "image_asset", "asset_id": "b",
             "panel_id": "p", "z_order": 2},
        ],
        "ports": [
            {"port_id": "a-out", "node_id": "a", "side": "right"},
            {"port_id": "b-in", "node_id": "b", "side": "left"},
        ],
        "typed_edges": [{
            "edge_id": "flow", "source_port": "a-out", "target_port": "b-in",
            "direction": "forward", "semantic_type": "activation",
        }],
        "groups": [{"group_id": "phase", "node_ids": ["a", "b"]}],
        "labels": [], "constraints": [],
    }


def _observed():
    return {
        "nodes": [{"node_id": "a"}, {"node_id": "b"}],
        "connectors": [{
            "edge_id": "flow", "source_port": "a-out", "target_port": "b-in",
            "direction": "forward",
        }],
        "groups": [{"group_id": "phase", "node_ids": ["a", "b"]}],
    }


def _manifest(elements):
    return LayoutManifest(
        schema_version="1.0", artifact_id="fixture",
        coordinate_system="pixel_top_left", canvas_width_px=1000,
        canvas_height_px=500, elements=elements,
    )


def _failed_checks(case, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    defect = case["defect"]
    graph = _graph()
    observed = _observed()
    if defect == "missing_node":
        observed["nodes"] = [{"node_id": "a"}]
        checks = validate_graph_structure(graph, observed)
    elif defect in {"reversed_edge", "broken_edge", "extra_edge", "bad_port_hit"}:
        if defect == "reversed_edge":
            observed["connectors"][0].update(
                source_port="b-in", target_port="a-out"
            )
        elif defect == "broken_edge":
            observed["connectors"] = []
        elif defect == "extra_edge":
            observed["connectors"].append({
                "edge_id": "extra", "source_port": "a-out",
                "target_port": "b-in", "direction": "forward",
            })
        else:
            observed["connectors"][0]["target_port"] = "wrong-port"
        checks = validate_graph_structure(graph, observed)
    elif defect in {"wrong_label", "wrong_formula"}:
        kind = "equation" if defect == "wrong_formula" else "label"
        element_id = "eq" if kind == "equation" else "label"
        content = "E = mc^2" if kind == "equation" else "Input"
        plan = {"text_elements": [{
            "element_id": element_id, "kind": kind, "content": content,
        }]}
        manifest = _manifest([LayoutElement(
            element_id=element_id,
            element_type="equation" if kind == "equation" else "text",
            bbox=PixelBBox(10, 10, 100, 30), text="wrong",
            font_size_pt=7, source="assembly",
        )])
        checks = formal_text_checks(plan, manifest, rendered_texts=["wrong"])
    elif defect == "unexpected_raster_text":
        checks = unexpected_ai_text([("asset", [LayoutElement(
            element_id="ocr", element_type="text",
            bbox=PixelBBox(1, 1, 20, 10), text="hallucination",
            source="ocr", metadata={"confidence": 0.99},
        )])])
    elif defect == "node_clipping":
        checks = asset_bounds(_manifest([LayoutElement(
            element_id="asset", element_type="image_asset",
            bbox=PixelBBox(-10, 0, 100, 100), source="assembly",
        )]), {})
    elif defect in {"node_overlap", "exclusion_overlap", "connector_crossing"}:
        if defect == "node_overlap":
            hints = {"a": [0.1, 0.1, 0.5, 0.5], "b": [0.3, 0.3, 0.5, 0.5]}
        else:
            graph["nodes"].append({
                "node_id": "obstacle", "node_type": "vector_element",
                "asset_id": "obstacle", "panel_id": "p", "z_order": 3,
            })
            hints = {
                "a": [0.1, 0.4, 0.2, 0.2], "b": [0.7, 0.4, 0.2, 0.2],
                "obstacle": [0.4, 0.3, 0.2, 0.4],
            }
            observed["nodes"].append({"node_id": "obstacle"})
            if defect == "exclusion_overlap":
                graph["typed_edges"] = []
                observed["connectors"] = []
                graph["constraints"] = [{
                    "kind": "exclude", "bbox": [0.4, 0.3, 0.2, 0.4],
                    "node_ids": ["obstacle"],
                }]
        solved = solve_figure_layout(
            graph, {"width": 180, "height": 90, "aspect_ratio": 2}, hints
        )
        checks = validate_graph_structure(
            graph, observed, conflicts=solved["conflicts"]
        )
    elif defect in {"missing_group", "wrong_group_membership"}:
        observed["groups"] = (
            [] if defect == "missing_group"
            else [{"group_id": "phase", "node_ids": ["a"]}]
        )
        checks = validate_graph_structure(graph, observed)
    elif defect == "inaccessible_colour":
        checks = [publication_accessibility_check(
            "nature_research", {"red": "#D62728", "green": "#2CA02C"}
        )]
    elif defect in {"noneditable_text", "bad_publication_width", "bad_font_size"}:
        font_size = 9 if defect == "bad_font_size" else 7
        checks = publication_profile_checks(
            "nature_research",
            _manifest([LayoutElement(
                element_id="label", element_type="text",
                bbox=PixelBBox(10, 10, 100, 30), text="Input",
                font_size_pt=font_size, source="assembly",
            )]),
            (140, 100) if defect == "bad_publication_width" else (89, 100),
            editable_svg_exists=defect != "noneditable_text",
        )
    elif defect == "blank_asset":
        image_path = tmp_path / "blank.png"
        Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)).save(image_path)
        checks = deterministic_image_checks(image_path)
    elif defect == "mask_leakage":
        parent = tmp_path / "parent.png"
        edited = tmp_path / "edited.png"
        mask = tmp_path / "mask.png"
        Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(parent)
        changed = Image.new("RGBA", (64, 64), (0, 0, 255, 255))
        ImageDraw.Draw(changed).ellipse((24, 24, 40, 40), fill=(255, 0, 0, 255))
        changed.save(edited)
        mask_image = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(mask_image).ellipse((24, 24, 40, 40), fill=255)
        mask_image.save(mask)
        outcome = evaluate_local_edit(parent, edited, mask_path=mask)
        return {"edit_outcome"} if not outcome["accepted"] else set()
    else:
        raise AssertionError(f"unhandled mechanism fixture: {defect}")
    return {
        check["check_id"] for check in checks
        if check.get("status") == "fail"
    }


def test_twenty_offline_mechanism_cases_execute_real_single_axis_validators(tmp_path):
    paths = sorted(CASES.glob("*.json"))
    cases = [json.loads(path.read_text()) for path in paths]

    assert len(cases) == 20
    assert len({case["case_id"] for case in cases}) == 20
    assert len({case["defect"] for case in cases}) == 20
    assert {case["axis"] for case in cases} == {
        "structure", "text", "geometry", "phase", "publication", "raster",
    }
    check_axes = {
        "graph_node_recovery": "structure",
        "graph_edge_recovery": "structure",
        "formal_text_exact_match": "text",
        "formula_exact_match": "text",
        "rendered_text_ocr_exact_match": "text",
        "rendered_formula_ocr_exact_match": "text",
        "unexpected_ai_text": "text",
        "asset_bounds": "geometry",
        "figure_layout_conflicts": "geometry",
        "graph_group_recovery": "phase",
        "publication_accessibility": "publication",
        "publication_editable_vectors": "publication",
        "publication_dimensions": "publication",
        "publication_typography": "publication",
        "blank_output": "raster",
        "edge_margins": "raster",
        "edit_outcome": "raster",
    }
    for case in cases:
        failures = _failed_checks(case, tmp_path / case["case_id"])
        assert case["expected_check_id"] in failures
        assert {check_axes[check_id] for check_id in failures} == {
            case["axis"]
        }, case
