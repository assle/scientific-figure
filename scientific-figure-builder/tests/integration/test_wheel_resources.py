from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_wheel_places_runtime_data_under_figure_tools(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required to inspect the built wheel")
    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert (
        "figure_tools/scientific_figure_builder_data/"
        "templates/default-project.yaml"
    ) in names
    assert (
        "figure_tools/scientific_figure_builder_data/"
        "schemas/run-state.schema.json"
    ) in names
