"""Data handling and exact source->render mapping validation tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from figure_tools.plotting.data import build_data_used, compute_content_hash, load_source_data
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.validation.plot_checks import validate_plot_data

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
CSV = FIXTURES / "coupling.csv"


def test_load_source_data_reads_csv() -> None:
    df = load_source_data(CSV)
    assert list(df.columns) == ["offset_um", "efficiency", "efficiency_std"]
    assert len(df) == 5
    assert df["efficiency"].iloc[2] == 98.0


def test_compute_content_hash_is_deterministic() -> None:
    h1 = compute_content_hash(CSV)
    h2 = compute_content_hash(CSV)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_build_data_used_is_exact_subset_of_source() -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    source = load_source_data(CSV)
    used = build_data_used(spec, source)
    # The plotted columns must be present and row counts must match the source
    # (no filters/transforms in this fixture).
    assert len(used) == len(source) == 5
    for series in spec.series:
        assert series["x"] in used.columns
        assert series["y"] in used.columns
    # Exact value equality against source for mapped columns.
    assert list(used["offset_um"]) == list(source["offset_um"])
    assert list(used["efficiency"]) == list(source["efficiency"])


def test_validate_plot_data_confirms_exact_mapping() -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    source = load_source_data(CSV)
    used = build_data_used(spec, source)
    report = validate_plot_data(spec, source_df=source, data_used_df=used)
    assert report["summary"]["errors"] == 0
    assert report["summary"]["blocking"] is False
    # Every check passed.
    assert all(c["status"] == "pass" for c in report["checks"])


def test_validate_plot_data_detects_hash_mismatch() -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    source = load_source_data(CSV)
    used = build_data_used(spec, source)
    # Tamper: change a plotted value but keep the original (mismatched) source.
    used = used.copy()
    used.loc[2, "efficiency"] = 0.0
    report = validate_plot_data(spec, source_df=source, data_used_df=used)
    assert report["summary"]["errors"] >= 1
    assert report["summary"]["blocking"] is True
    assert any(c["level"] == "error" and c["status"] == "fail" for c in report["checks"])


def test_build_data_used_applies_filter() -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    spec_dict = spec.to_dict()
    spec_dict["filters"] = [{"column": "offset_um", "op": ">=", "value": 0.0}]
    from figure_tools.plotting.spec import load_plot_spec as _load

    spec_filtered = _load(spec_dict)
    source = load_source_data(CSV)
    used = build_data_used(spec_filtered, source)
    assert len(used) == 3
    assert (used["offset_um"] >= 0.0).all()


def test_validate_plot_data_report_conforms_to_schema() -> None:
    import json

    from jsonschema import Draft202012Validator

    from figure_tools._resources import schema_path

    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    source = load_source_data(CSV)
    used = build_data_used(spec, source)
    report = validate_plot_data(spec, source_df=source, data_used_df=used)
    schema = json.loads(schema_path("validation-report.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(report))
    assert not errors, [e.message for e in errors]


def test_validate_plot_data_source_hash_mismatch() -> None:
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    spec_dict = spec.to_dict()
    spec_dict["source_data"]["content_hash"] = "sha256:deadbeef"
    from figure_tools.plotting.spec import load_plot_spec as _load

    spec_bad = _load(spec_dict)
    source = load_source_data(CSV)
    used = build_data_used(spec_bad, source)
    report = validate_plot_data(spec_bad, source_df=source, data_used_df=used, source_path=CSV)
    assert report["summary"]["errors"] >= 1
    assert any(c["check_id"] == "source_data_hash" and c["status"] == "fail"
               for c in report["checks"])

