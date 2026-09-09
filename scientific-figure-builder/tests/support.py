"""Shared black-box test artifacts."""

from __future__ import annotations

import zipfile
from pathlib import Path


def write_core_wheel(path: Path, version: str) -> Path:
    distribution = f"scientific_figure_builder-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{distribution}/METADATA",
            "Metadata-Version: 2.3\n"
            "Name: scientific-figure-builder\n"
            f"Version: {version}\n",
        )
        archive.writestr(
            f"{distribution}/WHEEL",
            "Wheel-Version: 1.0\nTag: py3-none-any\n",
        )
    return path
