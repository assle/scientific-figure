"""Deterministic plot-data validation (plan section 11).

Never relies on visual judgment for numerical accuracy: it compares the rendered
data against the source data deterministically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from figure_tools.plotting.data import build_data_used, compute_content_hash
from figure_tools.plotting.spec import PlotSpec
from figure_tools.validation.summary import make_check, summarize_checks


def _plotted_columns(spec: PlotSpec) -> list[str]:
    cols: list[str] = []
    for s in spec.series:
        cols += [s["x"], s["y"]]
    for e in spec.errors:
        if "y_err" in e:
            cols.append(e["y_err"])
        if "x_err" in e:
            cols.append(e["x_err"])
    # de-duplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def validate_plot_data(
    spec: PlotSpec,
    source_df: pd.DataFrame,
    data_used_df: pd.DataFrame,
    source_path: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    checks: list[dict] = []

    # 1. Exact source -> render mapping.
    expected = build_data_used(spec, source_df)
    try:
        pd.testing.assert_frame_equal(
            data_used_df.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_like=True,
            check_dtype=False,
        )
        checks.append(make_check("rendered_data_mapping", "plot", "error", "pass",
                             "rendered data exactly matches expected source mapping"))
    except AssertionError:
        checks.append(make_check("rendered_data_mapping", "plot", "error", "fail",
                             "rendered data does not match expected source mapping"))

    # 2. Columns and units.
    missing_cols = [c for c in _plotted_columns(spec) if c not in data_used_df.columns]
    unit_cols = [spec.axes["x"], spec.axes["y"]]
    missing_units = [c for c in unit_cols if c not in spec.units]
    if missing_cols or missing_units:
        detail = f"missing columns={missing_cols}; missing units={missing_units}"
        checks.append(make_check("columns_and_units", "plot", "error", "fail", detail))
    else:
        checks.append(make_check("columns_and_units", "plot", "error", "pass",
                             "all plotted columns and axis units present"))

    # 3. Sample counts.
    min_samples = spec.validation_expectations.get("min_samples")
    if min_samples is not None:
        n = len(data_used_df)
        if n < int(min_samples):
            checks.append(make_check("sample_count", "plot", "error", "fail",
                                 f"{n} samples < required {min_samples}"))
        else:
            checks.append(make_check("sample_count", "plot", "error", "pass",
                                 f"{n} samples >= required {min_samples}"))

    # 4. Missing-value handling (warning, not blocking).
    plotted = [c for c in _plotted_columns(spec) if c in data_used_df.columns]
    nan_count = int(data_used_df[plotted].isna().sum().sum()) if plotted else 0
    if nan_count:
        checks.append(make_check("missing_values", "plot", "warning", "fail",
                             f"{nan_count} missing values in plotted columns"))
    else:
        checks.append(make_check("missing_values", "plot", "warning", "pass",
                             "no missing values in plotted columns"))

    # 5. Transformations recorded.
    n_tr = len(spec.transformations)
    checks.append(make_check("transformations", "plot", "warning", "pass",
                         f"{n_tr} transformation(s) applied" if n_tr else "no transformations"))

    # 6. Error-bar definitions.
    bad_err = [e for e in spec.errors
               if ("y_err" in e and e["y_err"] not in data_used_df.columns)
               or ("x_err" in e and e["x_err"] not in data_used_df.columns)]
    if spec.errors and bad_err:
        checks.append(make_check("error_bar_definitions", "plot", "error", "fail",
                             "error-bar columns missing"))
    else:
        checks.append(make_check("error_bar_definitions", "plot", "error", "pass",
                             "error-bar columns present"))

    # 7. Source-data hash (only when the source file is available).
    if source_path is not None and Path(source_path).exists():
        actual = compute_content_hash(source_path)
        expected_hash = spec.source_data["content_hash"]
        if actual == expected_hash:
            checks.append(make_check("source_data_hash", "plot", "error", "pass",
                                 "source file hash matches spec"))
        else:
            checks.append(make_check("source_data_hash", "plot", "error", "fail",
                                 "source file hash does not match spec"))

    return {
        "schema_version": "1.0",
        "run_id": run_id or f"plot:{spec.source_data['path']}",
        "checks": checks,
        "summary": summarize_checks(checks),
    }
