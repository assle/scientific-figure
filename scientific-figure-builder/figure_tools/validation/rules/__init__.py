"""Deterministic layout rules (plan section 11)."""

from __future__ import annotations

from figure_tools.validation.rules.ai_asset import unexpected_ai_text
from figure_tools.validation.rules.colorbar import colorbar_collision
from figure_tools.validation.rules.clipping import asset_bounds, text_clipping
from figure_tools.validation.rules.overlap import text_text_overlap
from figure_tools.validation.rules.panel_labels import (
    panel_label_collision,
    panel_label_consistency,
)
from figure_tools.validation.rules.typography import minimum_font_size

__all__ = [
    "text_text_overlap",
    "text_clipping",
    "asset_bounds",
    "panel_label_collision",
    "panel_label_consistency",
    "minimum_font_size",
    "colorbar_collision",
    "unexpected_ai_text",
]
