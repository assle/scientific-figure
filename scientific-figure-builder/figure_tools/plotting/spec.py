"""Plot-spec loader and validator."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path

_VALIDATOR: Draft202012Validator | None = None


def _validator() -> Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = json.loads(schema_path("plot-spec.schema.json").read_text(encoding="utf-8"))
        _VALIDATOR = Draft202012Validator(schema)
    return _VALIDATOR


def validate_plot_spec(data: Mapping[str, Any]) -> None:
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.path))
    if errors:
        msg = "; ".join(f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors)
        raise ValueError(f"invalid plot spec: {msg}")


@dataclass
class PlotSpec:
    data: dict

    def __post_init__(self) -> None:
        validate_plot_spec(self.data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlotSpec":
        return cls(copy.deepcopy(dict(data)))

    def to_dict(self) -> dict:
        return copy.deepcopy(self.data)

    @property
    def schema_version(self) -> str:
        return self.data["schema_version"]

    @property
    def chart_type(self) -> str:
        return self.data["chart_type"]

    @property
    def recipe_version(self) -> str:
        return self.data["recipe_version"]

    @property
    def source_data(self) -> dict:
        return self.data["source_data"]

    @property
    def column_mapping(self) -> dict:
        return self.data["column_mapping"]

    @property
    def units(self) -> dict:
        return self.data["units"]

    @property
    def series(self) -> list:
        return self.data["series"]

    @property
    def errors(self) -> list:
        return self.data["errors"]

    @property
    def transformations(self) -> list:
        return self.data["transformations"]

    @property
    def filters(self) -> list:
        return self.data["filters"]

    @property
    def axes(self) -> dict:
        return self.data["axes"]

    @property
    def scales(self) -> dict:
        return self.data["scales"]

    @property
    def ticks(self) -> dict:
        return self.data["ticks"]

    @property
    def legends(self) -> list:
        return self.data["legends"]

    @property
    def labels(self) -> dict:
        return self.data["labels"]

    @property
    def figure(self) -> dict:
        return self.data["figure"]

    @property
    def export(self) -> dict:
        return self.data["export"]

    @property
    def validation_expectations(self) -> dict:
        return self.data["validation_expectations"]


def load_plot_spec(source: str | Path | Mapping[str, Any]) -> PlotSpec:
    if isinstance(source, Mapping):
        return PlotSpec.from_dict(source)
    path = Path(source)
    data = json.loads(path.read_text(encoding="utf-8"))
    return PlotSpec.from_dict(data)
