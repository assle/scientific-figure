"""Background removal for AI image assets (plan section 9 transparency workflow).

When the image model returns an opaque image (no alpha), the background is
removed so the asset becomes genuinely transparent. This is a lightweight,
deterministic edge-connected chroma key - no model download, reproducible.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def _edge_connected(mask: np.ndarray) -> np.ndarray:
    """Return the four-connected region of ``mask`` reachable from the canvas edge."""

    height, width = mask.shape
    connected = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    def add(y: int, x: int) -> None:
        if mask[y, x] and not connected[y, x]:
            connected[y, x] = True
            queue.append((y, x))

    for x in range(width):
        add(0, x)
        if height > 1:
            add(height - 1, x)
    for y in range(1, height - 1):
        add(y, 0)
        if width > 1:
            add(y, width - 1)

    while queue:
        y, x = queue.popleft()
        if y > 0:
            add(y - 1, x)
        if y + 1 < height:
            add(y + 1, x)
        if x > 0:
            add(y, x - 1)
        if x + 1 < width:
            add(y, x + 1)
    return connected


def remove_background(in_path: str | Path, out_path: str | Path,
                      tolerance: float = 30.0) -> bool:
    """Remove edge-connected pixels similar to the corner background as RGBA.

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
    similar_to_background = dist < tolerance
    background = _edge_connected(similar_to_background)
    alpha = np.where(background, 0, 255).astype(np.uint8)
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
