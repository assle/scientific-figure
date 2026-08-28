"""MCP server tool registry and dispatch tests (plan section 8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from figure_tools.server import PUBLIC_TOOLS, REQUIRED_TOOLS, TOOL_REGISTRY, _tool_list, dispatch

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"

REQUIRED = {
    "initialize_figure_project",
    "analyze_reference_figure",
    "check_figure_requirements",
    "create_figure_plan",
    "create_layout_wireframe",
    "generate_image_asset",
    "edit_image_asset",
    "render_scientific_plot",
    "render_vector_element",
    "validate_image_asset",
    "validate_plot_data",
    "assemble_figure",
    "validate_assembled_figure",
    "export_figure",
    "resume_figure_run",
    "advance_figure_workflow",
}


def test_registry_exposes_all_required_tools():
    assert set(REQUIRED_TOOLS) == REQUIRED
    for name in REQUIRED:
        assert name in TOOL_REGISTRY


def test_edit_tool_description_is_explicitly_generative_raster_only():
    description = TOOL_REGISTRY["edit_image_asset"]["description"]

    assert "generated or source-less raster" in description
    assert "plots and vectors" in description


def test_dispatch_initialize_figure_project(tmp_path: Path):
    result = dispatch("initialize_figure_project", {"project_dir": str(tmp_path)})
    assert (tmp_path / ".scientific-figure" / "project.yaml").is_file()
    assert "models" in result["config"]


def test_dispatch_create_figure_plan():
    request = {
        "figure_id": "f1", "canvas": {"aspect_ratio": 1.0, "width": 90, "height": 90},
        "units": "mm",
        "panels": [{"panel_id": "a", "bbox": [0, 0, 1, 1], "physical_size": [90, 90],
                    "elements": [{"element_id": "c", "type": "data_plot"}]}],
        "labels": [], "assumptions": [], "uncertainties": [],
        "user_input_requirements": [],
    }
    result = dispatch("create_figure_plan", {"request": request})
    plan = result["figure_plan"]
    assert plan["figure_id"] == "f1"
    assert plan["assets"][0]["routing"] == "python"


def test_registry_exposes_high_level_workflow_seam():
    schema = TOOL_REGISTRY["advance_figure_workflow"]["input_schema"]
    assert schema["type"] == "object"
    assert "run_dir" in schema["required"]
    assert "action" in schema["properties"]


def test_mcp_public_surface_exposes_only_lifecycle_entrypoints():
    assert PUBLIC_TOOLS == ["initialize_figure_project", "advance_figure_workflow"]
    assert [tool["name"] for tool in _tool_list()] == PUBLIC_TOOLS


def test_workflow_action_schema_requires_force_reason_and_rejects_unknown_fields():
    from jsonschema import Draft202012Validator

    schema = TOOL_REGISTRY["advance_figure_workflow"]["input_schema"]
    validator = Draft202012Validator(schema)
    base = {"run_dir": "/tmp/run"}
    assert list(validator.iter_errors({
        **base, "action": {"action": "force_export"},
    }))
    assert list(validator.iter_errors({
        **base, "action": {"action": "resume", "surprise": True},
    }))


def test_workflow_request_and_result_schemas_are_explicit():
    from jsonschema import Draft202012Validator

    tool = TOOL_REGISTRY["advance_figure_workflow"]
    input_validator = Draft202012Validator(tool["input_schema"])
    assert list(input_validator.iter_errors({
        "run_dir": "/tmp/run",
        "request": {"figure_id": "f", "panels": [], "surprise": True},
    }))
    output_schema = tool["output_schema"]
    assert output_schema["additionalProperties"] is False
    assert {"phase", "status", "next_action", "artifacts"} <= set(
        output_schema["required"]
    )


def test_every_tool_has_an_explicit_input_schema():
    for name in REQUIRED_TOOLS:
        schema = TOOL_REGISTRY[name]["input_schema"]
        assert schema.get("type") == "object"
        assert schema != {"type": "object"}, name


def test_dispatch_rejects_missing_required_arguments():
    with pytest.raises(ValueError, match="invalid arguments for render_scientific_plot"):
        dispatch("render_scientific_plot", {})


def test_dispatch_advance_figure_workflow(tmp_path: Path):
    request = {
        "figure_id": "f1", "canvas": {"aspect_ratio": 1.0, "width": 90, "height": 90},
        "units": "mm",
        "panels": [{"panel_id": "a", "bbox": [0, 0, 1, 1], "physical_size": [90, 90],
                    "elements": []}],
        "labels": [], "assumptions": [], "uncertainties": [],
        "user_input_requirements": [], "export_target": "general",
        "figure_width_cm": 14.0, "language": "en", "style": "default",
        "auto_execute": True,
    }
    run_dir = tmp_path / "run"
    result = dispatch("advance_figure_workflow", {
        "run_dir": str(run_dir), "request": request,
    })
    assert result["status"] == "completed"
    assert result["phase"] == "export"


def test_dispatch_check_figure_requirements():
    request = {
        "figure_id": "f1", "canvas": {"aspect_ratio": 1.0, "width": 90, "height": 90},
        "units": "mm",
        "panels": [{"panel_id": "a", "bbox": [0, 0, 1, 1], "physical_size": [90, 90],
                    "elements": [{"element_id": "c", "type": "data_plot"}]}],
        "labels": [], "assumptions": [], "uncertainties": [],
        "user_input_requirements": [],
    }
    result = dispatch("check_figure_requirements", {"request": request})
    assert result["blocked"] is True
    assert {r["field"] for r in result["requirements"]} == {
        "export_target", "figure_width_cm", "language", "style",
    }


def test_dispatch_check_figure_requirements_unblocked():
    request = {
        "figure_id": "f1", "canvas": {"aspect_ratio": 1.0, "width": 90, "height": 90},
        "units": "mm",
        "panels": [{"panel_id": "a", "bbox": [0, 0, 1, 1], "physical_size": [90, 90],
                    "elements": [{"element_id": "c", "type": "data_plot"}]}],
        "labels": [], "assumptions": [], "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
    }
    result = dispatch("check_figure_requirements", {"request": request})
    assert result["blocked"] is False
    assert result["requirements"] == []


def test_dispatch_render_scientific_plot_never_uses_generative_transport(
    tmp_path: Path, monkeypatch,
):
    import figure_tools.server as server

    monkeypatch.setattr(
        server,
        "_client",
        lambda *_args, **_kwargs: pytest.fail(
            "deterministic plot rendering must not construct a model client"
        ),
    )
    result = dispatch("render_scientific_plot", {
        "plot_spec_path": str(FIXTURES / "plot_spec_line.json"),
        "output_dir": str(tmp_path),
        "base_dir": str(ROOT),
    })
    assert (tmp_path / "plot.png").is_file()
    assert "data_used.csv" in result["files"]


@pytest.mark.parametrize(
    ("kind", "content"),
    [("label", "panel a"), ("equation", r"E=mc^2")],
)
def test_dispatch_render_vector_never_uses_generative_transport(
    monkeypatch, kind: str, content: str,
):
    import figure_tools.server as server

    monkeypatch.setattr(
        server,
        "_client",
        lambda *_args, **_kwargs: pytest.fail(
            "deterministic vector rendering must not construct a model client"
        ),
    )

    result = dispatch("render_vector_element", {"kind": kind, "content": content})

    assert "<svg" in result["svg"]


def test_dispatch_create_layout_wireframe():
    plan = json.loads((FIXTURES / "figure_plan.json").read_text(encoding="utf-8"))
    result = dispatch("create_layout_wireframe", {"figure_plan": plan})
    assert result["svg"].startswith("<svg")


def test_dispatch_unknown_tool_raises():
    import pytest

    with pytest.raises(KeyError):
        dispatch("no_such_tool", {})


def test_dispatch_generate_image_asset_isolated(tmp_path: Path):
    out = tmp_path / "a.png"
    result = dispatch("generate_image_asset",
                      {"prompt": "fiber", "output_path": str(out)})
    assert out.is_file()
    assert result["meta"]["transparent"] is True


@pytest.mark.parametrize("provider_name", ["custom", "ark"])
def test_configured_provider_key_does_not_require_global_ark_key(
    tmp_path: Path, monkeypatch, provider_name: str,
):
    import figure_tools.server as server
    from figure_tools.providers.transport import MockProviderTransport

    project = tmp_path / ".scientific-figure"
    project.mkdir()
    (project / "project.yaml").write_text(
        "models:\n"
        f"  image_generate: {{model: image-model, provider: {provider_name}}}\n"
        "providers:\n"
        f"  {provider_name}:\n"
        "    type: openai\n"
        "    base_url: https://models.example/v1\n"
        "    key_env: CUSTOM_API_KEY\n",
        encoding="utf-8",
    )
    custom_secret = f"custom-secret-{str(tmp_path).replace('/', '_')}"
    monkeypatch.setenv("CUSTOM_API_KEY", custom_secret)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    routed = []

    def provider_router(models, providers):
        routed.append((models, providers))
        return MockProviderTransport()

    monkeypatch.setattr(server, "ProviderRouter", provider_router)

    out = tmp_path / "asset.png"
    result = dispatch(
        "generate_image_asset",
        {
            "prompt": f"fiber {provider_name} {custom_secret}",
            "output_path": str(out),
            "project_dir": str(tmp_path),
        },
    )

    assert out.is_file()
    assert result["meta"]["model"] == "image-model"
    assert len(routed) == 1
    prompt_logs = list((tmp_path / "prompts").glob("*.txt"))
    assert len(prompt_logs) == 1
    assert custom_secret not in prompt_logs[0].read_text(encoding="utf-8")
    configured_client = server._client(project_dir=tmp_path)
    assert configured_client.state is not None
    assert "edits" not in configured_client.state.budget


# --- Spec 0001: export gate (rule lives in figure_tools/export/publish.py) ---

def test_dispatch_export_figure_wiring(tmp_path: Path):
    """Thin adapter smoke: the handler reads the on-disk final report and
    returns the shared export_figure result shape. Gate behavior itself is
    covered by tests/unit/test_publish.py."""
    run_dir = tmp_path / "run"
    assembly_dir = run_dir / "assembly"
    assembly_dir.mkdir(parents=True)
    (assembly_dir / "figure.png").write_bytes(b"fake-png")
    (assembly_dir / "figure.svg").write_text("<svg/>")
    vdir = run_dir / "validation"
    vdir.mkdir(parents=True)
    ok_report = {
        "schema_version": "1.0", "run_id": "final",
        "checks": [], "summary": {"errors": 0, "warnings": 0,
                                  "passed": 0, "blocking": False},
    }
    (vdir / "validation_report.json").write_text(
        json.dumps(ok_report), encoding="utf-8")
    output_dir = tmp_path / "exports"
    result = dispatch("export_figure", {
        "source_dir": str(assembly_dir), "output_dir": str(output_dir)})
    assert "png" in result["files"]
    assert "svg" in result["files"]
    assert result["export_blocked_reason"] is None
