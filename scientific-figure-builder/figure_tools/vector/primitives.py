"""SVG primitives: a small deterministic SVG canvas builder (plan section 6)."""

from __future__ import annotations

from xml.sax.saxutils import escape


class SvgCanvas:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self._defs: list[str] = []
        self._body: list[str] = []
        self._marker_n = 0

    @staticmethod
    def _attr_str(**kw: object) -> str:
        parts = []
        for k, v in kw.items():
            if v is None:
                continue
            parts.append(f'{k.replace("_", "-")}="{v}"')
        return " ".join(parts)

    def rect(self, x, y, w, h, **kw) -> None:
        self._body.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {self._attr_str(**kw)} />'
        )

    def line(self, x1, y1, x2, y2, **kw) -> None:
        self._body.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {self._attr_str(**kw)} />'
        )

    def circle(self, cx, cy, r, **kw) -> None:
        self._body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {self._attr_str(**kw)} />')

    def ellipse(self, cx, cy, rx, ry, **kw) -> None:
        self._body.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" {self._attr_str(**kw)} />'
        )

    def text(self, x, y, content, font_size: float = 10, **kw) -> None:
        escaped = escape(str(content))
        self._body.append(
            f'<text x="{x}" y="{y}" font-size="{font_size}" {self._attr_str(**kw)}>'
            f"{escaped}</text>"
        )

    def path(self, d, **kw) -> None:
        self._body.append(f'<path d="{d}" {self._attr_str(**kw)} />')

    def polyline(self, points, **kw) -> None:
        pts = " ".join(f"{x},{y}" for x, y in points)
        self._body.append(f'<polyline points="{pts}" {self._attr_str(**kw)} />')

    def polygon(self, points, **kw) -> None:
        pts = " ".join(f"{x},{y}" for x, y in points)
        self._body.append(f'<polygon points="{pts}" {self._attr_str(**kw)} />')

    def arrow(self, x1, y1, x2, y2, **kw) -> None:
        self._marker_n += 1
        marker_id = f"arrowhead_{self._marker_n}"
        self._defs.append(
            f'<marker id="{marker_id}" markerWidth="6" markerHeight="6" '
            f'refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{kw.get("stroke", "black")}" />'
            f"</marker>"
        )
        self._body.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'marker-end="url(#{marker_id})" {self._attr_str(**kw)} />'
        )

    def to_string(self) -> str:
        defs = "\n".join(self._defs)
        body = "\n".join(self._body)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">\n'
            f"{defs}\n{body}\n</svg>"
        )
