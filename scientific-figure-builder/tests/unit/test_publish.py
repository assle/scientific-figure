"""Export gate and publish deep-module tests (plan section 15).

The export decision and artifact copy live behind one interface,
``export_figure``, shared by the full workflow and the MCP tool. These tests
are the primary test surface for that module.
"""

from __future__ import annotations

from pathlib import Path

from figure_tools.export.publish import export_figure


def _assembly(tmp_path: Path) -> Path:
    src = tmp_path / "assembly"
    src.mkdir()
    (src / "figure.png").write_bytes(b"fake-png")
    (src / "figure.svg").write_text("<svg/>")
    (src / "figure.pdf").write_bytes(b"fake-pdf")
    return src


def _blocking_report() -> dict:
    return {
        "schema_version": "1.0", "run_id": "final",
        "checks": [{"check_id": "missing_assets", "scope": "final",
                     "level": "error", "status": "fail", "detail": "missing"}],
        "summary": {"errors": 1, "warnings": 0, "passed": 0, "blocking": True},
    }


def _ok_report() -> dict:
    return {
        "schema_version": "1.0", "run_id": "final",
        "checks": [{"check_id": "missing_assets", "scope": "final",
                     "level": "error", "status": "pass", "detail": "ok"}],
        "summary": {"errors": 0, "warnings": 0, "passed": 1, "blocking": False},
    }


def test_blocked_when_no_validation_reports(tmp_path: Path) -> None:
    result = export_figure([], source_dir=_assembly(tmp_path),
                           output_dir=tmp_path / "exports")
    assert result["files"] == {}
    assert "export_blocked_reason" in result
    assert not (tmp_path / "exports").exists()


def test_blocked_when_any_report_blocking(tmp_path: Path) -> None:
    result = export_figure(
        [_ok_report(), _blocking_report()],
        source_dir=_assembly(tmp_path), output_dir=tmp_path / "exports")
    assert result["files"] == {}
    assert "blocking errors" in result["export_blocked_reason"]


def test_force_export_bypasses_gate(tmp_path: Path) -> None:
    result = export_figure(
        [_blocking_report()],
        source_dir=_assembly(tmp_path), output_dir=tmp_path / "exports",
        force_export=True)
    assert "png" in result["files"]
    assert result["export_blocked_reason"] is None


def test_copies_artifacts_when_non_blocking(tmp_path: Path) -> None:
    src = _assembly(tmp_path)
    out = tmp_path / "exports"
    result = export_figure([_ok_report()], source_dir=src, output_dir=out)
    assert result["export_blocked_reason"] is None
    assert set(result["files"]) == {"png", "svg", "pdf"}
    for ext, path in result["files"].items():
        assert Path(path).read_bytes() == (src / f"figure.{ext}").read_bytes()


def test_formats_subset(tmp_path: Path) -> None:
    result = export_figure(
        [_ok_report()], source_dir=_assembly(tmp_path),
        output_dir=tmp_path / "exports", formats=("svg",))
    assert set(result["files"]) == {"svg"}
