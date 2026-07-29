"""LaTeX-to-SVG via matplotlib mathtext (plan section 10).

Uses matplotlib's built-in mathtext parser so no external TeX installation is
required. Output is deterministic.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from figure_tools.vector.svg_normalize import HASHSALT, normalize_svg_bytes  # noqa: E402


def latex_to_svg(latex: str, font_size: int = 10) -> str:
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.text(0.0, 0.0, f"${latex}$", fontsize=font_size)
    buf = io.BytesIO()
    try:
        with matplotlib.rc_context({"svg.hashsalt": HASHSALT, "text.usetex": False}):
            fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.02)
    finally:
        plt.close(fig)
    return normalize_svg_bytes(buf.getvalue()).decode("utf-8")
