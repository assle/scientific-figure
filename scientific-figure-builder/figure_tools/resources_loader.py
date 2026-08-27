"""Importlib-resources access for packaged GUI assets."""

from __future__ import annotations

from importlib.resources import files


def read_gui_resource(name: str) -> str:
    return files("figure_tools.resources").joinpath(name).read_text(encoding="utf-8")


__all__ = ["read_gui_resource"]
