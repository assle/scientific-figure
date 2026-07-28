"""LaTeX-to-SVG via matplotlib mathtext (plan section 10).

Uses matplotlib's built-in mathtext parser so no external TeX installation is
required. Output is deterministic.
"""

from __future__ import annotations

import io
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

_HASHSALT = "scientific-figure-builder"
_DATE_RE = re.compile(rb"<dc:date>.*?</dc:date>", re.DOTALL)
_COMMENT_RE = re.compile(rb"<!--.*?-->", re.DOTALL)


def latex_to_svg(latex: str, font_size: int = 10) -> str:
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.text(0.0, 0.0, f"${latex}$", fontsize=font_size)
    buf = io.BytesIO()
    try:
        with matplotlib.rc_context({"svg.hashsalt": _HASHSALT, "text.usetex": False}):
            fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.02)
    finally:
        plt.close(fig)
    data = buf.getvalue()
    data = _COMMENT_RE.sub(b"", data)
    data = _DATE_RE.sub(b"", data)
    return data.decode("utf-8")
