"""No-cost SVG layout wireframe generator (plan section 4 step 7)."""

from __future__ import annotations

from typing import Any

from figure_tools.vector.primitives import SvgCanvas


def generate_wireframe(figure_plan: dict[str, Any]) -> str:
    canvas = figure_plan["canvas"]
    w = float(canvas["width"])
    h = float(canvas["height"])
    c = SvgCanvas(width=w, height=h)

    # Canvas outline as a path so panel <rect> count stays exact.
    c.path(f"M 0 0 H {w} V {h} H 0 Z", stroke="#999999", fill="none", stroke_width=0.5)

    for panel in figure_plan["panels"]:
        bx, by, bw, bh = panel["bbox"]
        x = bx * w
        y = by * h
        pw = bw * w
        ph = bh * h
        c.rect(x, y, pw, ph, stroke="#333333", fill="#f5f5f5", stroke_width=0.75)
        c.text(x + 2, y + 9, panel["panel_id"], font_size=8, fill="#333333")
    return c.to_string()
