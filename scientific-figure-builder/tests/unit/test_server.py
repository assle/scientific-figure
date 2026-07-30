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


# --- Spec 0001: export validation gate ---

def _setup_export_dirs(tmp_path: Path, validation_report: dict | None):
    run_dir = tmp_path / "run"
    assembly_dir = run_dir / "assembly"
    assembly_dir.mkdir(parents=True)
    (assembly_dir / "figure.png").write_bytes(b"fake-png")
    (assembly_dir / "figure.svg").write_text("<svg/>")
    if validation_report is not None:
        vdir = run_dir / "validation"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "validation_report.json").write_text(
            json.dumps(validation_report), encoding="utf-8")
    return assembly_dir, run_dir


def test_export_blocked_when_no_validation_report(tmp_path: Path):
    assembly_dir, _ = _setup_export_dirs(tmp_path, None)
    output_dir = tmp_path / "exports"
    result = dispatch("export_figure", {
        "source_dir": str(assembly_dir), "output_dir": str(output_dir)})
    assert result["files"] == {}
    assert "export_blocked_reason" in result


def test_export_blocked_when_validation_blocking(tmp_path: Path):
    blocking_report = {
        "schema_version": "1.0", "run_id": "final",
        "checks": [{"check_id": "missing_assets", "scope": "final",
                     "level": "error", "status": "fail", "detail": "missing"}],
        "summary": {"errors": 1, "warnings": 0, "passed": 0, "blocking": True},
    }
    assembly_dir, _ = _setup_export_dirs(tmp_path, blocking_report)
    output_dir = tmp_path / "exports"
    result = dispatch("export_figure", {
        "source_dir": str(assembly_dir), "output_dir": str(output_dir)})
    assert result["files"] == {}
    assert "export_blocked_reason" in result


def test_export_succeeds_when_validation_non_blocking(tmp_path: Path):
    ok_report = {
        "schema_version": "1.0", "run_id": "final",
        "checks": [{"check_id": "missing_assets", "scope": "final",
                     "level": "error", "status": "pass", "detail": "ok"}],
        "summary": {"errors": 0, "warnings": 0, "passed": 1, "blocking": False},
    }
    assembly_dir, _ = _setup_export_dirs(tmp_path, ok_report)
    output_dir = tmp_path / "exports"
    result = dispatch("export_figure", {
        "source_dir": str(assembly_dir), "output_dir": str(output_dir)})
    assert "png" in result["files"]
    assert "svg" in result["files"]


def test_export_force_bypasses_gate(tmp_path: Path):
    blocking_report = {
        "schema_version": "1.0", "run_id": "final",
        "checks": [{"check_id": "missing_assets", "scope": "final",
                     "level": "error", "status": "fail", "detail": "missing"}],
        "summary": {"errors": 1, "warnings": 0, "passed": 0, "blocking": True},
    }
    assembly_dir, _ = _setup_export_dirs(tmp_path, blocking_report)
    output_dir = tmp_path / "exports"
    result = dispatch("export_figure", {
        "source_dir": str(assembly_dir), "output_dir": str(output_dir),
        "force_export": True})
    assert "png" in result["files"]
