"""Shared SVG normalization for byte-identical output (plan section 15)."""

from __future__ import annotations

import re

HASHSALT = "scientific-figure-builder"
_DATE_RE = re.compile(rb"<dc:date>.*?</dc:date>", re.DOTALL)
_COMMENT_RE = re.compile(rb"<!--.*?-->", re.DOTALL)


def normalize_svg_bytes(data: bytes) -> bytes:
    """Strip non-deterministic comments and dates from matplotlib SVG output."""
    data = _COMMENT_RE.sub(b"", data)
    data = _DATE_RE.sub(b"", data)
    return data
