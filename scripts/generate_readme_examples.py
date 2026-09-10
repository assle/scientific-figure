"""Generate the README example figures from synthetic demonstration data.

These images are illustrative product examples, not scientific evidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

REPOSITORY_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_DIR / "assets"
INK = "#101828"
MUTED = "#667085"
GRID = "#E4EAF2"
BORDER = "#D7DEE8"
PALETTE = {
    "blue": "#2563EB",
    "sky": "#0EA5E9",
    "teal": "#0F9D8F",
    "amber": "#F59E0B",
    "violet": "#7C3AED",
    "red": "#E25656",
}
LANDSCAPE = LinearSegmentedColormap.from_list(
    "scientific_figure_landscape",
    ["#123B72", "#3B82F6", "#DCEBFF", "#FDE7B0", "#F59E0B", "#9A3412"],
)
FIELD = LinearSegmentedColormap.from_list(
    "scientific_figure_field",
    ["#0F3B72", "#2563EB", "#7DD3FC", "#F8FAFC", "#FBBF24", "#B45309"],
)


def _configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "#FFFFFF",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": BORDER,
            "axes.labelcolor": MUTED,
            "axes.labelsize": 10,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"],
            "font.size": 9.5,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "legend.fontsize": 9,
            "legend.frameon": False,
            "savefig.facecolor": "#FFFFFF",
            "figure.dpi": 110,
        }
    )


def _finish_axes(ax: plt.Axes, *, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BORDER)
    ax.spines["bottom"].set_color(BORDER)
    ax.grid(True, axis=grid_axis, alpha=0.9)
    ax.set_axisbelow(True)


def _panel_title(ax: plt.Axes, text: str) -> None:
    ax.set_title(text, loc="left", pad=10)


def _save(fig: plt.Figure, destination: Path, *, dpi: int = 140) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=dpi, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)
    print(destination)


def _write_compound(output_dir: Path) -> None:
    rng = np.random.default_rng(42)
    fig = plt.figure(figsize=(12.8, 8.1))
    grid = fig.add_gridspec(
        2,
        6,
        left=0.055,
        right=0.965,
        bottom=0.08,
        top=0.855,
        hspace=0.42,
        wspace=0.95,
    )

    ax = fig.add_subplot(grid[0, 0:2])
    distance = np.linspace(0, 10, 28)
    efficiency = 4.8 + 49.0 * np.exp(-distance / 3.15) + rng.normal(0, 1.1, distance.size)
    error = 1.1 + 0.8 * distance / distance.max()
    ax.errorbar(
        distance,
        efficiency,
        yerr=error,
        color=PALETTE["blue"],
        marker="o",
        markersize=3.8,
        markeredgecolor="white",
        markeredgewidth=0.7,
        linewidth=2.0,
        capsize=2.5,
        elinewidth=1.0,
    )
    _panel_title(ax, "(a) Coupling decay")
    ax.set_xlabel("Distance (µm)")
    ax.set_ylabel("Efficiency (%)")
    ax.set_ylim(0, 58)
    _finish_axes(ax)

    ax = fig.add_subplot(grid[0, 2:6])
    periods = np.linspace(0, 40, 96)
    heights = np.linspace(0, 15, 61)
    period_grid, height_grid = np.meshgrid(periods, heights)
    landscape = (
        5.0
        + 3.8 * np.sin(period_grid / 3.4)
        - 0.16 * (height_grid - 7.5) ** 2
        + 4.2 * np.exp(
            -((period_grid - 10.5) ** 2 / 9.0 + (height_grid - 11.0) ** 2 / 8.0)
        )
        + 3.0 * np.exp(
            -((period_grid - 31.0) ** 2 / 11.0 + (height_grid - 5.5) ** 2 / 13.0)
        )
    )
    image = ax.imshow(
        landscape,
        origin="lower",
        aspect="auto",
        extent=[periods.min(), periods.max(), heights.min(), heights.max()],
        cmap=LANDSCAPE,
        interpolation="bilinear",
    )
    ax.contour(
        period_grid,
        height_grid,
        landscape,
        levels=7,
        colors="white",
        linewidths=0.65,
        alpha=0.55,
    )
    _panel_title(ax, "(b) Efficiency landscape")
    ax.set_xlabel("Period (nm)")
    ax.set_ylabel("Height (nm)")
    ax.grid(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.025)
    colorbar.set_label("Efficiency (%)", color=MUTED, fontsize=9)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=8.5, colors=MUTED)

    ax = fig.add_subplot(grid[1, 0:2])
    materials = ["SiO2", "TiO2", "Si3N4", "HfO2"]
    peak = np.array([42.5, 68.4, 54.7, 72.6])
    colors = [PALETTE["sky"], PALETTE["blue"], PALETTE["teal"], PALETTE["amber"]]
    bars = ax.bar(materials, peak, color=colors, width=0.62, edgecolor="white", linewidth=1.2)
    for bar, value in zip(bars, peak, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2.0,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            color=INK,
            fontsize=8.5,
        )
    _panel_title(ax, "(c) Material comparison")
    ax.set_ylabel("Peak efficiency (%)")
    ax.set_ylim(0, 82)
    _finish_axes(ax)

    ax = fig.add_subplot(grid[1, 2:4])
    parameter = np.linspace(0, 100, 54)
    merit = 0.79 * parameter + 4.2 * np.sin(parameter / 10.0) + rng.normal(0, 2.1, parameter.size)
    ax.scatter(
        parameter,
        merit,
        s=28,
        color=PALETTE["blue"],
        edgecolor="white",
        linewidth=0.6,
        alpha=0.86,
    )
    coefficients = np.polyfit(parameter, merit, 1)
    ax.plot(
        parameter,
        np.polyval(coefficients, parameter),
        color=PALETTE["amber"],
        linewidth=2.0,
    )
    _panel_title(ax, "(d) Parameter correlation")
    ax.set_xlabel("Design parameter")
    ax.set_ylabel("Figure of merit")
    _finish_axes(ax, grid_axis="both")

    ax = fig.add_subplot(grid[1, 4:6])
    phase = np.linspace(-2, 2, 181)
    amplitude = np.linspace(-2, 2, 181)
    phase_grid, amplitude_grid = np.meshgrid(phase, amplitude)
    radius = phase_grid**2 + (amplitude_grid / 1.35) ** 2
    field = 1.7 * np.exp(-radius / 0.55) - 0.65 * np.exp(-((radius - 2.1) ** 2) / 0.75)
    contour = ax.contourf(
        phase_grid,
        amplitude_grid,
        field,
        levels=16,
        cmap=FIELD,
        antialiased=True,
    )
    ax.contour(
        phase_grid,
        amplitude_grid,
        field,
        levels=7,
        colors="white",
        linewidths=0.55,
        alpha=0.5,
    )
    _panel_title(ax, "(e) Field distribution")
    ax.set_xlabel("Phase")
    ax.set_ylabel("Amplitude")
    ax.grid(False)
    colorbar = fig.colorbar(contour, ax=ax, fraction=0.045, pad=0.025)
    colorbar.set_label("Normalized field", color=MUTED, fontsize=8.5)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=8, colors=MUTED)

    fig.suptitle(
        "Illustrative multipanel study",
        x=0.055,
        y=0.965,
        ha="left",
        va="bottom",
        fontsize=16,
        fontweight="bold",
        color=INK,
    )
    fig.text(
        0.056,
        0.925,
        "Synthetic demonstration data",
        ha="left",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    _save(fig, output_dir / "example_compound.png")


def _write_line_plot(output_dir: Path) -> None:
    rng = np.random.default_rng(7)
    offset = np.linspace(-3, 3, 121)
    theoretical = 100.0 * np.exp(-((offset / 1.12) ** 2))
    measured = theoretical * (1.0 + 0.008 * np.sin(2.7 * offset)) + rng.normal(0, 0.55, offset.size)
    spread = 0.7 + 2.2 * np.abs(offset) / 3.0

    fig, ax = plt.subplots(figsize=(8.4, 5.2), constrained_layout=True)
    ax.fill_between(
        offset,
        measured - spread,
        measured + spread,
        color=PALETTE["sky"],
        alpha=0.16,
        linewidth=0,
        label="95% interval",
    )
    ax.plot(
        offset,
        theoretical,
        color=MUTED,
        linewidth=1.5,
        linestyle=(0, (5, 3)),
        label="Theoretical fit",
    )
    ax.errorbar(
        offset[::5],
        measured[::5],
        yerr=spread[::5],
        color=PALETTE["blue"],
        linewidth=2.2,
        marker="o",
        markersize=4.5,
        markeredgecolor="white",
        markeredgewidth=0.8,
        capsize=3,
        elinewidth=1.0,
        label="Measured",
    )
    peak = measured[np.argmax(theoretical)]
    ax.annotate(
        f"Peak {peak:.1f}%",
        xy=(0, peak),
        xytext=(0.95, 78),
        color=INK,
        fontsize=9.5,
        arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 1.0},
    )
    _panel_title(ax, "Coupling efficiency vs. lateral offset")
    ax.set_xlabel("Lateral offset (µm)")
    ax.set_ylabel("Coupling efficiency (%)")
    ax.set_xlim(-3.2, 3.2)
    ax.set_ylim(-5, 108)
    ax.legend(loc="upper right", ncol=3)
    _finish_axes(ax)
    _save(fig, output_dir / "example_line_plot.png")


def _write_heatmap(output_dir: Path) -> None:
    periods = np.linspace(0, 40, 121)
    heights = np.linspace(0, 16, 81)
    period_grid, height_grid = np.meshgrid(periods, heights)
    efficiency = (
        4.0
        + 4.8 * np.sin(period_grid / 4.1 + 0.4)
        - 0.13 * (height_grid - 8.0) ** 2
        + 5.7 * np.exp(
            -((period_grid - 12.5) ** 2 / 10.0 + (height_grid - 11.4) ** 2 / 6.5)
        )
        + 4.1 * np.exp(
            -((period_grid - 29.0) ** 2 / 15.0 + (height_grid - 5.2) ** 2 / 8.0)
        )
    )
    fig, ax = plt.subplots(figsize=(8.4, 5.5), constrained_layout=True)
    image = ax.imshow(
        efficiency,
        origin="lower",
        aspect="auto",
        extent=[periods.min(), periods.max(), heights.min(), heights.max()],
        cmap=LANDSCAPE,
        interpolation="bilinear",
    )
    contours = ax.contour(
        period_grid,
        height_grid,
        efficiency,
        levels=9,
        colors="white",
        linewidths=0.7,
        alpha=0.62,
    )
    ax.clabel(contours, inline=True, fontsize=7.5, fmt="%.0f", colors="#F8FAFC")
    best_index = np.unravel_index(np.argmax(efficiency), efficiency.shape)
    best_height = heights[best_index[0]]
    best_period = periods[best_index[1]]
    ax.scatter(
        [best_period],
        [best_height],
        s=46,
        facecolor="white",
        edgecolor=INK,
        linewidth=1.1,
        zorder=4,
    )
    ax.annotate(
        "Best region",
        xy=(best_period, best_height),
        xytext=(best_period + 4.5, min(best_height + 2.0, 14.6)),
        color=INK,
        fontsize=9.5,
        arrowprops={"arrowstyle": "->", "color": INK, "linewidth": 1.0},
    )
    _panel_title(ax, "Efficiency landscape")
    ax.set_xlabel("Period (nm)")
    ax.set_ylabel("Height (nm)")
    ax.grid(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02)
    colorbar.set_label("Efficiency (%)", color=MUTED, fontsize=9.5)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=9, colors=MUTED)
    _save(fig, output_dir / "example_heatmap.png")


def _write_multipanel(output_dir: Path) -> None:
    time = np.linspace(0, 10, 500)
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.6), sharey=True, constrained_layout=True)
    phases = (0.0, np.pi / 4.0, np.pi / 2.0)
    labels = ("0 degrees", "45 degrees", "90 degrees")
    for index, (ax, phase, label) in enumerate(zip(axes, phases, labels, strict=True)):
        response = np.exp(-0.09 * time) * np.sin(1.55 * time + phase)
        response += 0.08 * np.sin(4.2 * time + index * 0.35)
        ax.axhline(0, color=BORDER, linewidth=0.9)
        ax.plot(
            time,
            response,
            color=(PALETTE["blue"], PALETTE["teal"], PALETTE["violet"])[index],
            linewidth=2.1,
        )
        ax.fill_between(time, response, 0, color=ax.lines[-1].get_color(), alpha=0.08)
        _panel_title(ax, f"({chr(97 + index)}) Phase {label}")
        ax.set_xlabel("Time (a.u.)")
        ax.set_ylim(-1.15, 1.15)
        _finish_axes(ax)
    axes[0].set_ylabel("Normalized response")
    _save(fig, output_dir / "example_multipanel.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    _configure_style()
    _write_compound(output_dir)
    _write_line_plot(output_dir)
    _write_heatmap(output_dir)
    _write_multipanel(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
