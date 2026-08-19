"""MCP server tool registry and dispatch tests (plan section 8)."""

from __future__ import annotations

import json
from pathlib import Path

from figure_tools.server import REQUIRED_TOOLS, TOOL_REGISTRY, dispatch

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
}


def test_registry_exposes_all_required_tools():
    assert set(REQUIRED_TOOLS) == REQUIRED
    for name in REQUIRED:
        assert name in TOOL_REGISTRY


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


def test_dispatch_render_scientific_plot(tmp_path: Path):
    result = dispatch("render_scientific_plot", {
        "plot_spec_path": str(FIXTURES / "plot_spec_line.json"),
        "output_dir": str(tmp_path),
        "base_dir": str(ROOT),
    })
    assert (tmp_path / "plot.png").is_file()
    assert "data_used.csv" in result["files"]


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


def test_custom_provider_key_does_not_require_global_ark_key(
    tmp_path: Path, monkeypatch,
):
    import figure_tools.server as server
    from figure_tools.ark.transport import MockArkTransport

    project = tmp_path / ".scientific-figure"
    project.mkdir()
    (project / "project.yaml").write_text(
        "models:\n"
        "  image_generate: {model: image-model, provider: custom}\n"
        "providers:\n"
        "  custom:\n"
        "    type: openai\n"
        "    base_url: https://models.example/v1\n"
        "    key_env: CUSTOM_API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-secret")
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setattr(
        server,
        "ProviderRouter",
        lambda _models, _providers: MockArkTransport(),
    )

    out = tmp_path / "asset.png"
    result = dispatch(
        "generate_image_asset",
        {"prompt": "fiber", "output_path": str(out), "project_dir": str(tmp_path)},
    )

    assert out.is_file()
    assert result["meta"]["model"] == "image-model"


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
