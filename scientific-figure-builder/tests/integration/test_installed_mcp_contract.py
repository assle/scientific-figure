"""Installed-runtime contract verification for the public Lifecycle MCP."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_source_install_exposes_current_panel_and_operation_contracts(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is required for installed-runtime verification")
    install_home = tmp_path / "install"
    command = [
        str(REPOSITORY_ROOT / "install.sh"), "--runtime-only",
        "--install-home", str(install_home),
        "--bin-dir", str(tmp_path / "bin"),
        "--config-home", str(tmp_path / "config"),
        "--data-home", str(tmp_path / "data"),
        "--state-home", str(tmp_path / "state"),
        "--cache-home", str(tmp_path / "cache"),
        "--session-home", str(tmp_path / "session"),
        "--codex-home", str(tmp_path / "codex"),
    ]
    installed = subprocess.run(
        command, cwd=REPOSITORY_ROOT, check=True,
        capture_output=True, text=True, timeout=180,
    )
    assert "Scientific Figure Builder installed successfully" in installed.stdout

    active = json.loads(
        (install_home / "global/active-runtime.json").read_text(encoding="utf-8")
    )
    runtime = Path(active["runtime_dir"])
    python = runtime / ".venv/bin/python"
    script = (
        "import json; from figure_tools.server import _tool_list; "
        "tool=_tool_list()[1]; panel=tool['inputSchema']['properties']['request']"
        "['properties']['panels']['items']; print(json.dumps({'required':panel['required'],"
        "'fields':sorted(panel['properties']),"
        "'bbox_items':[panel['properties']['bbox']['minItems'],panel['properties']['bbox']['maxItems']],"
        "'physical_items':[panel['properties']['physical_size']['minItems'],panel['properties']['physical_size']['maxItems']],"
        "'element_required':panel['properties']['elements']['items']['required'],"
        "'element_types':sorted(panel['properties']['elements']['items']['properties']['type']['enum']),"
        "'statuses':tool['outputSchema']['properties']['status']['enum']}))"
    )
    checked = subprocess.run(
        [str(python), "-c", script], cwd=runtime, check=True,
        capture_output=True, text=True, timeout=30,
    )
    contract = json.loads(checked.stdout)
    assert contract["required"] == ["panel_id"]
    assert contract["fields"] == ["bbox", "elements", "panel_id", "physical_size"]
    assert contract["bbox_items"] == [4, 4]
    assert contract["physical_items"] == [2, 2]
    assert contract["element_required"] == ["element_id", "type"]
    assert contract["element_types"] == [
        "annotation", "data_plot", "equation", "image_asset", "label",
        "text", "vector_element",
    ]
    assert contract["statuses"] == ["in_progress", "paused", "completed"]
