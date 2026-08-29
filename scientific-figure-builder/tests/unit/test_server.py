"""MCP tests exercise only the public JSON-RPC surface."""

from __future__ import annotations

import io
import json
from pathlib import Path

import figure_tools.server as server
from figure_tools.runtime_context import RuntimeContextFactory


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def _rpc(monkeypatch, *messages):
    incoming = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    outgoing = io.StringIO()
    monkeypatch.setattr(server.sys, "stdin", incoming)
    monkeypatch.setattr(server.sys, "stdout", outgoing)
    assert server.serve_stdio() == 0
    return [json.loads(line) for line in outgoing.getvalue().splitlines()]


def _request():
    return {
        "figure_id": "mcp-figure",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": [{
            "panel_id": "a",
            "bbox": [0, 0, 1, 1],
            "physical_size": [180, 112.5],
            "elements": [{
                "element_id": "curve",
                "type": "data_plot",
                "plot_spec": str(FIXTURES / "plot_spec_line.json"),
            }],
        }],
        "labels": [],
        "assumptions": [],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "auto_execute": True,
    }


def test_initialize_and_tools_list_expose_exactly_two_public_tools(monkeypatch):
    responses = _rpc(
        monkeypatch,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert responses[0]["result"]["serverInfo"]["name"] == "scientific-figure"
    tools = responses[1]["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "initialize_figure_project",
        "advance_figure_workflow",
    ]
    assert "outputSchema" in tools[1]


def test_public_initialize_call_and_hidden_tool_rejection(monkeypatch, tmp_path):
    responses = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "initialize_figure_project",
                "arguments": {"project_dir": str(tmp_path)},
            },
        },
        {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "render_scientific_plot", "arguments": {}},
        },
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert payload["config"]["schema_version"] == "1.0"
    assert responses[1]["error"]["code"] == -32601
    assert "unknown tool" in responses[1]["error"]["message"]


def test_public_schema_rejection_happens_at_tools_call(monkeypatch):
    response = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {}},
        },
    )[0]

    assert response["error"]["code"] == -32603
    assert "run_dir" in response["error"]["message"]


def test_advance_call_delegates_through_runtime_context_and_orchestrator(
    monkeypatch, tmp_path
):
    factory = RuntimeContextFactory(
        config_loader=lambda _project: {"models": {}, "providers": {}},
        environ={},
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(server, "RuntimeContextFactory", lambda: factory)
    response = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "advance_figure_workflow",
                "arguments": {
                    "project_dir": str(tmp_path),
                    "run_dir": str(tmp_path / "run"),
                    "base_dir": str(ROOT),
                    "request": _request(),
                },
            },
        },
    )[0]

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "completed"
    assert payload["phase"] == "export"
    assert (tmp_path / "run" / "plans" / "figure_plan.json").is_file()


def test_runtime_errors_are_redacted_before_protocol_output(monkeypatch, tmp_path):
    class Client:
        def clean_error(self, error):
            return str(error).replace("sk-secret", "***REDACTED***")

    class Factory:
        def create(self, project_dir, run_dir):
            return type("Context", (), {
                "effective_config": {},
                "client": Client(),
                "state": object(),
                "worker": object(),
            })()

    class BrokenOrchestrator:
        def __init__(self, **kwargs):
            pass

        def advance(self, action):
            raise RuntimeError("provider rejected sk-secret")

    monkeypatch.setattr(server, "RuntimeContextFactory", Factory)
    monkeypatch.setattr(server, "FigureOrchestrator", BrokenOrchestrator)
    response = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "advance_figure_workflow",
                "arguments": {"run_dir": str(tmp_path / "run")},
            },
        },
    )[0]

    assert "sk-secret" not in response["error"]["message"]
    assert "***REDACTED***" in response["error"]["message"]
