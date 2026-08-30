"""Built-in publication constraints, kept separate from visual style."""

from __future__ import annotations

import copy
from typing import Any


_PROFILES: dict[str, dict[str, Any]] = {
    "general": {
        "profile_id": "general",
        "editable_vectors": True,
    },
    "nature_research": {
        "profile_id": "nature_research",
        "widths_mm": [89, 183],
        "maximum_height_mm": 170,
        "ordinary_text_pt": [5, 7],
        "panel_label_pt": 8,
        "font_families": ["Arial", "Helvetica"],
        "line_width_pt": [0.25, 1.0],
        "editable_vectors": True,
        "accessible_colours": True,
        "forbidden_elements": [
            "coloured_text",
            "drop_shadows",
            "decorative_icons",
            "busy_label_backgrounds",
            "unnecessary_gridlines",
        ],
    },
}


def get_publication_profile(profile_id: str) -> dict[str, Any]:
    try:
        return copy.deepcopy(_PROFILES[profile_id])
    except KeyError as exc:
        raise ValueError(f"unknown Publication profile {profile_id!r}") from exc


__all__ = ["get_publication_profile"]
