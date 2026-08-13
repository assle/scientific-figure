"""LaTeX-to-SVG via matplotlib mathtext (plan section 10).

Uses matplotlib's built-in mathtext parser so no external TeX installation is
required. Output is deterministic.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from figure_tools.vector.svg_normalize import (  # noqa: E402
    HASHSALT,
    normalize_svg_bytes,
    resolve_export_target,
)


def latex_to_svg(latex: str, font_size: int = 10,
                 export_target: str = "general") -> str:
    export_target = resolve_export_target(export_target)
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.text(0.0, 0.0, f"${latex}$", fontsize=font_size)
    buf = io.BytesIO()
    try:
        rc = {"svg.hashsalt": HASHSALT, "text.usetex": False}
        if export_target == "ppt":
            # Equations stay as vector shapes rather than editable text.
            rc["svg.fonttype"] = "path"
        with matplotlib.rc_context(rc):
            fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.02)
    finally:
        plt.close(fig)
    return normalize_svg_bytes(buf.getvalue(), export_target=export_target).decode("utf-8")
