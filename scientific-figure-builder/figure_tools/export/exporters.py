"""Deterministic figure exporters (plan section 15, Phase 2 exit criteria).

Repeated execution must produce byte-identical local artifacts. Timestamps and
other non-deterministic metadata are normalized or stripped.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive; safe in headless/CI

from PIL import Image  # noqa: E402
from figure_tools.vector.svg_normalize import (  # noqa: E402
    HASHSALT,
    normalize_svg_bytes,
    resolve_export_target,
)

# Font family used for PowerPoint-ready SVG (export_target="ppt"). Arial covers
# Latin text, SimSun (宋体) covers Chinese, sans-serif is the final fallback.
PPT_FONT_FAMILY = ["Arial", "SimSun", "sans-serif"]


_PDF_METADATA = {
    "Creator": "scientific-figure-builder",
    "Producer": "scientific-figure-builder",
    "CreationDate": datetime(2000, 1, 1),
    "ModDate": datetime(2000, 1, 1),
}


def export_png(fig, path: Path, dpi: int = 300) -> Path:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    buf.seek(0)
    img = Image.open(buf)
    img.load()
    # Re-encode without metadata for byte-identical output.
    img.save(path, format="PNG", optimize=False, pnginfo=None)
    return path


def export_svg(fig, path: Path, export_target: str = "general") -> Path:
    export_target = resolve_export_target(export_target)
    buf = io.BytesIO()
    rc = matplotlib.RcParams({"svg.hashsalt": HASHSALT})
    if export_target == "ppt":
        rc["svg.fonttype"] = "none"
        rc["font.family"] = PPT_FONT_FAMILY
    with matplotlib.rc_context(rc):
        fig.savefig(buf, format="svg")
    path.write_bytes(normalize_svg_bytes(buf.getvalue(), export_target=export_target))
    return path


def export_pdf(fig, path: Path) -> Path:
    fig.savefig(path, format="pdf", metadata=_PDF_METADATA)
    return path


def save_figure(fig, out_dir: Path, basename: str = "plot",
                formats=("png", "svg", "pdf"), dpi: int = 300,
                export_target: str = "general") -> dict[str, Path]:
    export_target = resolve_export_target(export_target)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[str, Path] = {}
    if "png" in formats:
        produced["png"] = export_png(fig, out_dir / f"{basename}.png", dpi=dpi)
    if "svg" in formats:
        produced["svg"] = export_svg(fig, out_dir / f"{basename}.svg",
                                     export_target=export_target)
    if "pdf" in formats:
        produced["pdf"] = export_pdf(fig, out_dir / f"{basename}.pdf")
    return produced
