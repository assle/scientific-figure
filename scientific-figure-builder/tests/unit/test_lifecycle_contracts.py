from jsonschema import Draft202012Validator

from figure_tools.lifecycle_contracts import FIGURE_REQUEST_SCHEMA, WORKFLOW_INPUT_SCHEMA


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

    assert not list(Draft202012Validator(FIGURE_REQUEST_SCHEMA).iter_errors(request))


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

    assert not list(Draft202012Validator(WORKFLOW_INPUT_SCHEMA).iter_errors(action))
