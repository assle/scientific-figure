from __future__ import annotations

import shutil
import subprocess
import json
import os
import sys
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
    assert (
        "figure_tools/scientific_figure_builder_data/"
        "schemas/planning-advice.schema.json"
    ) in names
    assert (
        "figure_tools/scientific_figure_builder_data/"
        "schemas/phase-operation.schema.json"
    ) in names

    extracted = tmp_path / "wheel"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(extracted)
    command = (
        "import json; from figure_tools.server import _tool_list; "
        "print(json.dumps(_tool_list()[1]['inputSchema']['properties']"
        "['request']['properties']['panels']['items']))"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(extracted)
    completed = subprocess.run(
        [sys.executable, "-c", command], cwd=tmp_path, env=environment,
        check=True, capture_output=True, text=True,
    )
    panel_schema = json.loads(completed.stdout)
    assert panel_schema["required"] == ["panel_id"]
    assert set(panel_schema["properties"]) >= {
        "panel_id", "bbox", "physical_size", "elements",
    }
