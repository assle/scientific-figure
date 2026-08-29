"""Source-data loading, content hashing, and exact data_used construction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from figure_tools.plotting.spec import PlotSpec
from figure_tools.provenance import hash_file

_FILTER_OPS = {
    ">=": lambda s, v: s >= v,
    "<=": lambda s, v: s <= v,
    ">": lambda s, v: s > v,
    "<": lambda s, v: s < v,
    "==": lambda s, v: s == v,
    "!=": lambda s, v: s != v,
}


def load_source_data(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".json":
        return pd.read_json(path)
    return pd.read_csv(path)


def compute_content_hash(path: str | Path) -> str:
    return hash_file(path)


def _apply_filter(df: pd.DataFrame, flt: dict) -> pd.DataFrame:
    col = flt["column"]
    op = flt["op"]
    value = flt["value"]
    if op == "between":
        lo, hi = value
        return df[(df[col] >= lo) & (df[col] <= hi)]
    if op == "in":
        return df[df[col].isin(value)]
    if op not in _FILTER_OPS:
        raise ValueError(f"unsupported filter op: {op}")
    return df[_FILTER_OPS[op](df[col], value)]


def _apply_transformation(df: pd.DataFrame, tr: dict) -> pd.DataFrame:
    col = tr["column"]
    op = tr["op"]
    target = tr.get("as", col)
    if op == "log10":
        df[target] = np.log10(df[col])
    elif op == "multiply":
        df[target] = df[col] * tr["value"]
    elif op == "add":
        df[target] = df[col] + tr["value"]
    elif op == "subtract":
        df[target] = df[col] - tr["value"]
    elif op == "divide":
        df[target] = df[col] / tr["value"]
    else:
        raise ValueError(f"unsupported transformation op: {op}")
    return df


def build_data_used(spec: PlotSpec, source_df: pd.DataFrame) -> pd.DataFrame:
    """Return the exact DataFrame that will be plotted (filters + transforms applied)."""
    df = source_df.copy()
    for flt in spec.filters:
        df = _apply_filter(df, flt)
    for tr in spec.transformations:
        df = _apply_transformation(df, tr)
    return df.reset_index(drop=True)
