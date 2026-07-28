"""Locate bundled package data (schemas, templates) in dev or installed layouts."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent  # .../scientific-figure-builder/
_INSTALLED_DATA = "scientific_figure_builder_data"


def _dev_path(*parts: str) -> Path | None:
    candidate = _PKG_ROOT.joinpath(*parts)
    return candidate if candidate.exists() else None


def schema_path(name: str) -> Path:
    dev = _dev_path("schemas", name)
    if dev is not None:
        return dev
    res = resources.files("figure_tools").joinpath(_INSTALLED_DATA, "schemas", name)
    return Path(str(res))


def template_path(name: str) -> Path:
    dev = _dev_path("templates", name)
    if dev is not None:
        return dev
    res = resources.files("figure_tools").joinpath(_INSTALLED_DATA, "templates", name)
    return Path(str(res))


def templates_dir() -> Path:
    dev = _dev_path("templates")
    if dev is not None:
        return dev
    return Path(str(resources.files("figure_tools").joinpath(_INSTALLED_DATA, "templates")))
