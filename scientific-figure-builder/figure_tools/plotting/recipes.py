"""Fixed, tested plot recipes (plan section 15, Phase 2).

Each recipe consumes a PlotSpec and the exact data_used DataFrame and returns a
matplotlib Figure. Recipes are deterministic: identical inputs yield identical
figures.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from figure_tools._resources import template_path
from figure_tools.plotting.spec import PlotSpec

_STYLE = None


def _style() -> str:
    global _STYLE
    if _STYLE is None:
        _STYLE = str(template_path("publication.mplstyle"))
    return _STYLE


def _apply_axes(ax, spec: PlotSpec) -> None:
    scales = spec.scales
    if "x" in scales:
        ax.set_xscale(scales["x"])
    if "y" in scales:
        ax.set_yscale(scales["y"])
    ticks = spec.ticks
    if "x" in ticks:
        ax.set_xticks(ticks["x"])
    if "y" in ticks:
        ax.set_yticks(ticks["y"])
    labels = spec.labels
    ax.set_title(labels.get("title", ""))
    ax.set_xlabel(labels.get("x", ""))
    ax.set_ylabel(labels.get("y", ""))
    if any(s.get("label") for s in spec.series):
        loc = "best"
        if spec.legends:
            loc = spec.legends[0].get("loc", "best")
        ax.legend(loc=loc)


def _err_column_for(spec: PlotSpec, series_id: str) -> str | None:
    for e in spec.errors:
        if e.get("series_id") == series_id and "y_err" in e:
            return e["y_err"]
    return None


def render_line(spec: PlotSpec, df) -> plt.Figure:
    with plt.style.context(_style()):
        fig, ax = plt.subplots(figsize=spec.figure["dimensions"])
        for s in spec.series:
            err = _err_column_for(spec, s["series_id"])
            if err and err in df.columns:
                ax.errorbar(df[s["x"]], df[s["y"]], yerr=df[err], label=s.get("label"),
                            fmt="-o", capsize=2)
            else:
                ax.plot(df[s["x"]], df[s["y"]], "-o", label=s.get("label"))
        _apply_axes(ax, spec)
        fig.tight_layout()
    return fig


def render_scatter(spec: PlotSpec, df) -> plt.Figure:
    with plt.style.context(_style()):
        fig, ax = plt.subplots(figsize=spec.figure["dimensions"])
        for s in spec.series:
            ax.scatter(df[s["x"]], df[s["y"]], label=s.get("label"))
        _apply_axes(ax, spec)
        fig.tight_layout()
    return fig


def render_bar(spec: PlotSpec, df) -> plt.Figure:
    with plt.style.context(_style()):
        fig, ax = plt.subplots(figsize=spec.figure["dimensions"])
        for s in spec.series:
            ax.bar(df[s["x"]], df[s["y"]], label=s.get("label"))
        _apply_axes(ax, spec)
        fig.tight_layout()
    return fig


def render_heatmap(spec: PlotSpec, df) -> plt.Figure:
    with plt.style.context(_style()):
        fig, ax = plt.subplots(figsize=spec.figure["dimensions"])
        s = spec.series[0]
        x_col, y_col = s["x"], s["y"]
        if "z" in df.columns:
            pivot = df.pivot_table(index=y_col, columns=x_col, values="z")
            ax.imshow(pivot.values, aspect="auto",
                      extent=[pivot.columns.min(), pivot.columns.max(),
                              pivot.index.min(), pivot.index.max()],
                      origin="lower")
        else:
            ax.hist2d(df[x_col], df[y_col], bins=10)
        labels = spec.labels
        ax.set_title(labels.get("title", ""))
        ax.set_xlabel(labels.get("x", ""))
        ax.set_ylabel(labels.get("y", ""))
        fig.tight_layout()
    return fig


def render_error_bar(spec: PlotSpec, df) -> plt.Figure:
    with plt.style.context(_style()):
        fig, ax = plt.subplots(figsize=spec.figure["dimensions"])
        for s in spec.series:
            err = _err_column_for(spec, s["series_id"])
            yerr = df[err] if err and err in df.columns else None
            ax.errorbar(df[s["x"]], df[s["y"]], yerr=yerr, fmt="o-", capsize=2,
                        label=s.get("label"))
        _apply_axes(ax, spec)
        fig.tight_layout()
    return fig


def render_multipanel(spec: PlotSpec, df) -> plt.Figure:
    with plt.style.context(_style()):
        n = max(1, len(spec.series))
        fig, axes = plt.subplots(1, n, figsize=(spec.figure["dimensions"][0] * n,
                                                spec.figure["dimensions"][1]))
        if n == 1:
            axes = [axes]
        for ax, s in zip(axes, spec.series):
            err = _err_column_for(spec, s["series_id"])
            if err and err in df.columns:
                ax.errorbar(df[s["x"]], df[s["y"]], yerr=df[err], fmt="-o", capsize=2,
                            label=s.get("label"))
            else:
                ax.plot(df[s["x"]], df[s["y"]], "-o", label=s.get("label"))
            ax.set_title(s.get("label", s["series_id"]))
            labels = spec.labels
            ax.set_xlabel(labels.get("x", ""))
            ax.set_ylabel(labels.get("y", ""))
        fig.tight_layout()
    return fig


RECIPES = {
    "line": render_line,
    "scatter": render_scatter,
    "bar": render_bar,
    "heatmap": render_heatmap,
    "error_bar": render_error_bar,
    "multipanel": render_multipanel,
}


def render(spec: PlotSpec, df) -> plt.Figure:
    try:
        recipe = RECIPES[spec.chart_type]
    except KeyError:
        raise ValueError(f"no recipe for chart_type {spec.chart_type!r}")
    return recipe(spec, df)
