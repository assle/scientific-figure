"""Thin stdio MCP Adapter for the public scientific-figure lifecycle."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from figure_tools import __version__
from figure_tools.config import initialize_project
from figure_tools.lifecycle_contracts import (
    INITIALIZE_INPUT_SCHEMA,
    WORKFLOW_INPUT_SCHEMA,
    WORKFLOW_OUTPUT_SCHEMA,
)
from figure_tools.orchestrator import FigureOrchestrator
from figure_tools.runtime_context import RuntimeContextFactory


PUBLIC_TOOLS = ("initialize_figure_project", "advance_figure_workflow")


class PublicToolError(RuntimeError):
    """A tool failure whose message is already safe for the protocol boundary."""


def _project_dir_for(arguments: Mapping[str, Any]) -> Path:
    explicit = arguments.get("project_dir") or os.environ.get(
        "SCIENTIFIC_FIGURE_PROJECT_DIR"
    )
    if explicit:
        return Path(str(explicit))
    run_dir = Path(str(arguments.get("run_dir", ".")))
    for candidate in (run_dir, *run_dir.parents):
        if (candidate / ".scientific-figure").is_dir():
            return candidate
    return Path(str(arguments.get("base_dir", ".")))


def _initialize(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"config": initialize_project(arguments["project_dir"])}


def _advance(arguments: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(arguments["run_dir"])
    project_dir = _project_dir_for(arguments)
    try:
        context = RuntimeContextFactory().create(project_dir, run_dir)
    except Exception as exc:  # construction errors are already secret-safe
        raise PublicToolError(str(exc)) from exc
    orchestrator = FigureOrchestrator(
        request=arguments.get("request"),
        config=context.effective_config,
        run_dir=run_dir,
        provider_client=context.client,
        state=context.state,
        base_dir=arguments.get("base_dir", "."),
        compose_dpi=int(arguments.get("dpi", 300)),
        worker=context.worker,
    )
    try:
        return orchestrator.advance(arguments.get("action"))
    except Exception as exc:  # noqa: BLE001 - redaction belongs at this adapter
        raise PublicToolError(context.client.clean_error(exc)) from exc


_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "initialize_figure_project": {
        "description": "Create non-secret Project configuration.",
        "input_schema": INITIALIZE_INPUT_SCHEMA,
        "handler": _initialize,
    },
    "advance_figure_workflow": {
        "description": "Advance one lifecycle transition through the Orchestrator.",
        "input_schema": WORKFLOW_INPUT_SCHEMA,
        "output_schema": WORKFLOW_OUTPUT_SCHEMA,
        "handler": _advance,
    },
}


def _validate(value: Any, schema: Mapping[str, Any], label: str) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise PublicToolError(f"invalid {label}: {detail}")


def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    spec = _TOOL_SPECS.get(name)
    if spec is None:
        raise KeyError(name)
    _validate(arguments, spec["input_schema"], f"arguments for {name}")
    handler: Callable[[dict[str, Any]], Any] = spec["handler"]
    result = handler(arguments)
    if "output_schema" in spec:
        _validate(result, spec["output_schema"], f"result for {name}")
    return result


def _tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": _TOOL_SPECS[name]["description"],
            "inputSchema": _TOOL_SPECS[name]["input_schema"],
            **(
                {"outputSchema": _TOOL_SPECS[name]["output_schema"]}
                if "output_schema" in _TOOL_SPECS[name]
                else {}
            ),
        }
        for name in PUBLIC_TOOLS
    ]


def serve_stdio() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        method = message.get("method")
        message_id = message.get("id")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "scientific-figure", "version": __version__},
            }
        elif method == "tools/list":
            result = {"tools": _tool_list()}
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            try:
                data = _call_tool(str(name), params.get("arguments") or {})
            except KeyError:
                _write_error(message_id, -32601, f"unknown tool {name!r}")
                continue
            except Exception as exc:  # messages are redacted by _advance
                _write_error(message_id, -32603, str(exc))
                continue
            result = {
                "content": [{"type": "text", "text": json.dumps(data, default=str)}]
            }
        else:
            _write_error(message_id, -32601, f"unknown method {method}")
            continue
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0", "id": message_id, "result": result,
        }) + "\n")
        sys.stdout.flush()
    return 0


def _write_error(message_id: Any, code: int, message: str) -> None:
    sys.stdout.write(json.dumps({
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
