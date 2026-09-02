from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from figure_tools.provider_configuration import (
    MODEL_ROLE_CATALOG,
    MODEL_ROLES,
    PROVIDER_TYPES,
    configured_model_routes,
    effective_model_route,
    normalize_provider,
    normalize_providers,
    route_compatibility,
    provider_capabilities_for_role,
)


def test_provider_configuration_is_headless_and_catalog_is_canonical():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import figure_tools.provider_configuration; "
                "raise SystemExit(1 if 'PySide6' in sys.modules else 0)"
            ),
        ],
        cwd=Path(__file__).parents[2],
        check=False,
    )
    assert result.returncode == 0
    assert PROVIDER_TYPES == ("openai", "anthropic")
    assert tuple(item.role for item in MODEL_ROLE_CATALOG) == MODEL_ROLES
    edit = next(item for item in MODEL_ROLE_CATALOG if item.role == "image_edit")
    assert edit.inherits_from == "image_generate"
    assert edit.required_capability == "supports_image_edit"


@pytest.mark.parametrize(
    ("protocol", "provider_type"),
    [("responses", "openai"), ("anthropic", "anthropic")],
)
def test_every_legacy_protocol_migrates_to_a_provider_type(protocol, provider_type):
    with pytest.warns(FutureWarning):
        provider = normalize_provider("legacy", {"protocol": protocol, "base_url": "https://x/v1"})
    assert provider["type"] == provider_type
    assert "protocol" not in provider


def test_conflicting_legacy_and_current_provider_metadata_is_rejected():
    with pytest.raises(ValueError, match="conflicting type"):
        normalize_provider("broken", {"type": "openai", "protocol": "anthropic"})


def test_normalization_removes_fields_for_the_other_provider_type_and_adds_defaults():
    anthropic = normalize_provider("p", {
        "type": "anthropic",
        "base_url": "https://example.test/v1/messages",
        "supports_image_edit": True,
    })
    assert anthropic["base_url"] == "https://example.test"
    assert "supports_image_edit" not in anthropic
    assert anthropic["messages_path"] == "/messages"

    openai = normalize_provider("p", {
        **anthropic,
        "type": "openai",
        "supports_image_edit": True,
    })
    assert "messages_path" not in openai
    assert "anthropic_version" not in openai
    assert openai["supports_image_edit"] is True

    defaults = normalize_provider("p", {
        "type": "anthropic",
        "auth_scheme": None,
        "messages_path": "",
    })
    assert defaults["auth_scheme"] == "x-api-key"
    assert defaults["messages_path"] == "/messages"


def test_model_routes_ignore_placeholders_apply_environment_and_inherit_image_edit():
    models = configured_model_routes({
        "models": {
            "image_generate": {"provider": "images", "model": "gen-v1"},
            "vision_validate": {"provider": "vision", "model": "<fixed-model-or-endpoint-id>"},
        }
    }, environ={"SCI_FIG_VISION_VALIDATE": "vision-v2"})

    assert models["vision_validate"]["model"] == "vision-v2"
    assert effective_model_route("image_edit", models) == models["image_generate"]


def test_route_compatibility_uses_provider_type_and_declared_capabilities():
    models = {
        "image_generate": {"provider": "images", "model": "gen"},
        "vision_validate": {"provider": "claude", "model": "vision"},
    }
    providers = normalize_providers({
        "images": {"type": "openai", "supports_image_edit": False},
        "claude": {"type": "anthropic"},
    })

    assert route_compatibility("image_generate", models, providers).compatible
    assert route_compatibility("vision_validate", models, providers).compatible
    edit = route_compatibility("image_edit", models, providers)
    assert not edit.compatible
    assert "supports_image_edit" in edit.reason


def test_openai_provider_normalizes_generation_capabilities():
    provider = normalize_provider("images", {
        "type": "openai",
        "supports_reference_image": True,
        "supports_multi_reference": True,
        "supports_mask_edit": True,
        "supports_structure_control": True,
        "supports_native_alpha": True,
        "supports_seed": True,
        "supports_candidate_batch": True,
    })

    assert provider["supports_reference_image"] is True
    assert provider["supports_multi_reference"] is True
    assert provider["supports_mask_edit"] is True
    assert provider["supports_structure_control"] is True
    assert provider["supports_native_alpha"] is True
    assert provider["supports_seed"] is True
    assert provider["supports_candidate_batch"] is True


def test_provider_capability_query_returns_only_normalized_capabilities():
    capabilities = provider_capabilities_for_role(
        "image_generate",
        {"image_generate": {"provider": "images", "model": "gen"}},
        {"images": {
            "type": "openai",
            "base_url": "https://models.example/v1",
            "supports_reference_image": True,
        }},
        adapter_capabilities={"supports_mask_edit": True, "base_url": "ignored"},
    )

    assert capabilities["supports_reference_image"] is True
    assert capabilities["supports_mask_edit"] is False
    assert "base_url" not in capabilities
