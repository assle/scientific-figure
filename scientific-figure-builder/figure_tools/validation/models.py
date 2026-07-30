"""Core data models for image QA layout manifests (plan section 6).

All bounding boxes use a single coordinate convention within one manifest:
origin at the top-left corner of the canvas, units in pixels, stored as
``[x1, y1, x2, y2]``. Matplotlib's bottom-left display coordinates are
converted to this convention by the extractors; the models themselves are
coordinate-system agnostic and only carry a ``coordinate_system`` label.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args

ElementType = Literal[
    "panel",
    "image_asset",
    "data_region",
    "text",
    "panel_label",
    "axis_label",
    "tick_label",
    "title",
    "legend",
    "colorbar",
    "equation",
]

VALID_ELEMENT_TYPES: frozenset[str] = frozenset(get_args(ElementType))


@dataclass(frozen=True)
class PixelBBox:
    """Axis-aligned bounding box in pixels: ``[x1, y1, x2, y2]``."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        # Normalise so x1<=x2 and y1<=y2 (frozen -> use object.__setattr__).
        # Capture originals first; setattr mutates in place.
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        if x1 > x2 or y1 > y2:
            object.__setattr__(self, "x1", min(x1, x2))
            object.__setattr__(self, "x2", max(x1, x2))
            object.__setattr__(self, "y1", min(y1, y2))
            object.__setattr__(self, "y2", max(y1, y2))

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    @classmethod
    def from_list(cls, bbox: list[float] | tuple[float, float, float, float]) -> "PixelBBox":
        if len(bbox) != 4:
            raise ValueError(f"bbox must have 4 values, got {len(bbox)}")
        x1, y1, x2, y2 = (float(v) for v in bbox)
        return cls(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


@dataclass
class LayoutElement:
    element_id: str
    element_type: ElementType
    bbox: PixelBBox
    panel_id: str | None = None
    text: str | None = None
    font_size_pt: float | None = None
    rotation_deg: float = 0.0
    z_order: int = 0
    source: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.element_type not in VALID_ELEMENT_TYPES:
            raise ValueError(f"unknown element_type: {self.element_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type,
            "bbox": self.bbox.as_list(),
            "panel_id": self.panel_id,
            "text": self.text,
            "font_size_pt": self.font_size_pt,
            "rotation_deg": self.rotation_deg,
            "z_order": self.z_order,
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LayoutElement":
        return cls(
            element_id=data["element_id"],
            element_type=data["element_type"],
            bbox=PixelBBox.from_list(data["bbox"]),
            panel_id=data.get("panel_id"),
            text=data.get("text"),
            font_size_pt=data.get("font_size_pt"),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            z_order=int(data.get("z_order", 0)),
            source=data.get("source", "unknown"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class LayoutManifest:
    schema_version: str
    artifact_id: str
    coordinate_system: str
    canvas_width_px: int
    canvas_height_px: int
    elements: list[LayoutElement]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "coordinate_system": self.coordinate_system,
            "canvas": {
                "width_px": self.canvas_width_px,
                "height_px": self.canvas_height_px,
            },
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LayoutManifest":
        canvas = data["canvas"]
        return cls(
            schema_version=data["schema_version"],
            artifact_id=data["artifact_id"],
            coordinate_system=data["coordinate_system"],
            canvas_width_px=int(canvas["width_px"]),
            canvas_height_px=int(canvas["height_px"]),
            elements=[LayoutElement.from_dict(e) for e in data.get("elements", [])],
        )


def write_layout_manifest(path: str | Path, manifest: LayoutManifest) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest.to_dict(), indent=2),
        encoding="utf-8",
    )
    return out


def read_layout_manifest(path: str | Path) -> LayoutManifest:
    return LayoutManifest.from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


__all__ = [
    "ElementType",
    "VALID_ELEMENT_TYPES",
    "PixelBBox",
    "LayoutElement",
    "LayoutManifest",
    "write_layout_manifest",
    "read_layout_manifest",
]
