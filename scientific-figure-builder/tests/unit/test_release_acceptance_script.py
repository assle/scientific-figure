"""Real local convergence acceptance evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "record_release_acceptance.py"


def _module():
    spec = importlib.util.spec_from_file_location("record_release_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_requires_observed_new_task_mcp_and_configuration_app() -> None:
    status = {
        "conclusion": "converged",
        "target_version": "0.6.0",
        "cli_version": "0.6.0",
        "plugin": {"version": "0.6.0", "installed": True, "enabled": True},
        "stale_instances": [],
        "clean": True,
        "running_instances": [
            {"kind": "mcp", "version": "0.6.0"},
            {"kind": "gui", "version": "0.6.0"},
        ],
    }

    evidence = _module().acceptance_from_status(
        status, confirm_codex_restart=True,
    )
    assert evidence["mcp_version"] == "0.6.0"
    assert evidence["configuration_app_version"] == "0.6.0"

    status["running_instances"] = status["running_instances"][:1]
    with pytest.raises(RuntimeError, match="Configuration app"):
        _module().acceptance_from_status(status, confirm_codex_restart=True)
