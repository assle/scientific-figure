"""Deterministic acceptance and rollback evidence for localized raster edits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from figure_tools.validation.image_checks import deterministic_image_checks
from figure_tools.validation.summary import summarize_checks


def evaluate_local_edit(
    parent_path: str | Path,
    edited_path: str | Path,
    *,
    mask_path: str | Path | None = None,
    physical_size_mm: tuple[float, float] | None = None,
    maximum_unmasked_difference: float = 2.0,
    target_improved: bool | None = None,
) -> dict[str, Any]:
    original_summary = summarize_checks(
        deterministic_image_checks(parent_path, physical_size_mm)
    )
    edited_summary = summarize_checks(
        deterministic_image_checks(edited_path, physical_size_mm)
    )
    unmasked_difference = 0.0
    if mask_path is not None:
        original = np.asarray(Image.open(parent_path).convert("RGBA"), dtype=np.float32)
        edited = np.asarray(Image.open(edited_path).convert("RGBA"), dtype=np.float32)
        mask = np.asarray(Image.open(mask_path).convert("L"))
        if original.shape != edited.shape or mask.shape != original.shape[:2]:
            return {
                "accepted": False,
                "reason": "edit and mask dimensions do not match the parent",
                "original_summary": original_summary,
                "edited_summary": edited_summary,
                "unmasked_mean_absolute_difference": None,
            }
        unmasked = mask < 128
        if np.any(unmasked):
            unmasked_difference = float(
                np.mean(np.abs(original[unmasked] - edited[unmasked]))
            )
    accepted = not bool(edited_summary["blocking"])
    reason = "edited asset passed Deterministic checks"
    if not accepted:
        reason = "edited asset failed Deterministic checks"
    elif unmasked_difference > maximum_unmasked_difference:
        accepted = False
        reason = "edit changed pixels outside the mask"
    elif target_improved is False:
        accepted = False
        reason = "edited asset did not improve the target check"
    return {
        "accepted": accepted,
        "reason": reason,
        "original_summary": original_summary,
        "edited_summary": edited_summary,
        "unmasked_mean_absolute_difference": round(unmasked_difference, 6),
    }


__all__ = ["evaluate_local_edit"]
