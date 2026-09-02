from __future__ import annotations

import pytest

from figure_tools.generation_conditions import (
    GenerationConditionError,
    compile_generation_condition,
)


def _request(**overrides):
    request = {
        "asset_id": "cell",
        "model_role": "image_generate",
        "scientific_intent": "show a receptor activating an intracellular pathway",
        "prompt": "isolated membrane receptor and cell membrane",
        "style_bible": {
            "palette": {"primary": "#4477AA", "accent": "#EE6677"},
            "view": "isometric",
            "projection": "oblique",
            "lighting": "soft top-left light",
            "material": "matte",
            "background": "transparent",
            "shadow": "none",
            "forbidden_elements": ["watermarks", "decorative scenes"],
        },
        "style_bible_hash": "sha256:style-a",
        "publication_profile": {
            "profile_id": "nature_research",
            "font_family": "Arial",
            "ordinary_text_pt": [5, 7],
            "editable_vectors": True,
        },
        "publication_profile_hash": "sha256:profile-a",
        "parameters": {"size": "2048x2048", "seed": 7},
        "references": [],
        "provider_capabilities": {},
    }
    request.update(overrides)
    return request


def test_generation_condition_is_deterministic_and_compiles_style_contract():
    first = compile_generation_condition(_request())
    second = compile_generation_condition(_request())

    assert first == second
    assert first["asset_id"] == "cell"
    assert first["condition_hash"].startswith("sha256:")
    assert first["parameters"] == {"seed": 7, "size": "2048x2048"}
    assert "isometric" in first["prompt"]
    assert "#4477AA" in first["prompt"]
    assert "no text" in first["negative_constraints"]
    assert "no watermark" in first["negative_constraints"]


def test_style_change_changes_the_condition_identity():
    changed = _request()
    changed["style_bible"] = {
        **changed["style_bible"],
        "view": "orthographic",
    }
    changed["style_bible_hash"] = "sha256:style-b"

    assert (
        compile_generation_condition(_request())["condition_hash"]
        != compile_generation_condition(changed)["condition_hash"]
    )


def test_reference_roles_require_declared_provider_capabilities():
    reference = {
        "role": "style",
        "path": "/references/anchor.png",
        "content_hash": "sha256:anchor",
        "strength": 0.75,
    }

    with pytest.raises(GenerationConditionError, match="supports_reference_image"):
        compile_generation_condition(_request(references=[reference]))

    compiled = compile_generation_condition(_request(
        references=[reference],
        provider_capabilities={"supports_reference_image": True},
    ))

    assert compiled["references"] == [reference]
    assert compiled["condition_hash"] != compile_generation_condition(_request())[
        "condition_hash"
    ]


def test_generation_condition_rejects_secret_bearing_input():
    with pytest.raises(GenerationConditionError, match="secret-bearing"):
        compile_generation_condition(_request(api_key="do-not-persist"))
