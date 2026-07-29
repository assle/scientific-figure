"""Background removal for AI image assets (plan section 9 transparency workflow).

When the image model returns an opaque image (no alpha), the background is
removed so the asset becomes genuinely transparent. This is a lightweight,
deterministic corner-seeded chroma key - no model download, reproducible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def remove_background(in_path: str | Path, out_path: str | Path,
                      tolerance: float = 30.0) -> bool:
    """Remove the corner-seeded background and write an RGBA PNG.

    Returns True if the result has an alpha channel with transparent pixels.
    """
    img = Image.open(in_path).convert("RGB")
    arr = np.array(img)  # HxWx3
    h, w = arr.shape[:2]
    pad = max(4, min(h, w) // 64)

    # Background color = median of the four corner patches.
    corners = np.concatenate([
        arr[:pad, :pad].reshape(-1, 3),
        arr[:pad, -pad:].reshape(-1, 3),
        arr[-pad:, :pad].reshape(-1, 3),
        arr[-pad:, -pad:].reshape(-1, 3),
    ])
    bg = np.median(corners, axis=0)

    dist = np.sqrt(((arr.astype(np.float32) - bg) ** 2).sum(axis=2))
    fg = dist >= tolerance  # foreground mask
    alpha = np.where(fg, 255, 0).astype(np.uint8)
    rgba = np.dstack([arr, alpha])

    out = Image.fromarray(rgba, "RGBA")
    out_path = Path(out_path)
    out.save(out_path, format="PNG")

    transparent_pixels = int((alpha == 0).sum())
    return transparent_pixels > 0


def ensure_transparency(path: str | Path) -> bool:
    """If the image has no alpha, remove the background. Returns True if the
    final image has (and uses) an alpha channel."""
    img = Image.open(path)
    if "A" in img.getbands():
        return True
    return remove_background(path, path)
