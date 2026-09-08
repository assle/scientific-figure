import json

from figure_tools.lifecycle_contracts import FIGURE_REQUEST_SCHEMA, WORKFLOW_INPUT_SCHEMA
from figure_tools.run_store import schema_error_detail
from figure_tools._resources import template_path


def test_public_request_contract_accepts_structure_and_generation_controls():
    request = {
        "figure_id": "mechanism",
        "panels": [{
            "panel_id": "a",
            "bbox": [0, 0, 1, 1],
            "physical_size": [89, 80],
            "elements": [{
                "element_id": "cell",
                "type": "image_asset",
                "prompt": "cell",
                "bbox": [0.1, 0.1, 0.8, 0.8],
                "candidate_count": 2,
                "style_group": "biology",
                "references": [{
                    "role": "style",
                    "path": "/references/style.png",
                    "content_hash": "sha256:style",
                    "strength": 0.75,
                }],
            }],
        }],
        "publication_profile": "nature_research",
        "figure_graph": {
            "ports": [], "typed_edges": [], "groups": [], "labels": [],
            "constraints": [],
        },
    }

    assert schema_error_detail(request, FIGURE_REQUEST_SCHEMA) is None


def test_public_repair_contract_accepts_local_patch_operations():
    action = {
        "run_dir": "/runs/mechanism",
        "action": {
            "action": "apply_repair",
            "repairs": [{
                "asset_id": "cell",
                "operation": "layout_patch",
                "bbox": [0.1, 0.1, 0.8, 0.8],
                "bbox_space": "panel",
            }],
        },
    }

    assert schema_error_detail(action, WORKFLOW_INPUT_SCHEMA) is None


def test_public_style_contract_accepts_canonical_and_legacy_inputs():
    base = {
        "figure_id": "styles",
        "panels": [{"panel_id": "main"}],
    }
    style_bible = json.loads(
        template_path("default-style-bible.json").read_text(encoding="utf-8")
    )
    values = [
        "default",
        "flat orthographic scientific graphic",
        {"kind": "default"},
        {"kind": "description", "description": "flat scientific graphic"},
        {"kind": "file", "path": "/tmp/style.json"},
        style_bible,
        {"kind": "inline", "style_bible": style_bible},
    ]
    for style in values:
        request = {**base, "style": style}
        assert schema_error_detail(request, FIGURE_REQUEST_SCHEMA) is None
