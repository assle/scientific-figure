"""MCP tests exercise only the public JSON-RPC surface."""

from __future__ import annotations

import io
import json
import time
from dataclasses import replace
from pathlib import Path

import figure_tools.server as server
from figure_tools.runtime_context import RuntimeContextFactory
from figure_tools.state import RunState
from figure_tools.phase_workers import StructuredPhaseWorker
from figure_tools.run_store import RunStore


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def _rpc(monkeypatch, *messages, continue_summaries=True):
    incoming = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    outgoing = io.StringIO()
    monkeypatch.setattr(server.sys, "stdin", incoming)
    monkeypatch.setattr(server.sys, "stdout", outgoing)
    original = server._call_tool
    def continue_plan(name, arguments):
        data = original(name, arguments)
        if data.get("generation_summary") and data.get("next_action") == "resume":
            continuation = {key: value for key, value in arguments.items() if key != "request"}
            data = original(name, {**continuation, "action": "resume"})
        return data
    with monkeypatch.context() as scoped:
        if continue_summaries:
            scoped.setattr(server, "_call_tool", continue_plan)
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


def _use_offline_runtime(monkeypatch, tmp_path):
    factory = RuntimeContextFactory(
        config_loader=lambda _project: {"models": {}, "providers": {}},
        environ={},
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(server, "RuntimeContextFactory", lambda: factory)
    return factory


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
    panel = (
        tools[1]["inputSchema"]["properties"]["request"]
        ["properties"]["panels"]["items"]
    )
    assert panel["required"] == ["panel_id"]
    assert set(panel["properties"]) >= {
        "panel_id", "bbox", "physical_size", "elements",
    }
    assert panel["properties"]["bbox"]["minItems"] == 4
    assert panel["properties"]["bbox"]["maxItems"] == 4
    assert panel["properties"]["physical_size"]["minItems"] == 2
    assert panel["properties"]["physical_size"]["maxItems"] == 2
    element = panel["properties"]["elements"]["items"]
    assert element["required"] == ["element_id", "type"]
    assert set(element["properties"]["type"]["enum"]) == {
        "data_plot", "image_asset", "label", "annotation", "text",
        "equation", "vector_element",
    }


def test_single_panel_geometry_is_derived_after_canvas_resolution(monkeypatch, tmp_path):
    _use_offline_runtime(monkeypatch, tmp_path)
    request = _request()
    request["auto_execute"] = False
    request["panels"] = [{
        "panel_id": "a",
        "elements": [{
            "element_id": "curve", "type": "data_plot",
            "plot_spec": str(FIXTURES / "plot_spec_line.json"),
        }],
    }]
    run_dir = tmp_path / "default-panel"

    response = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(run_dir), "request": request,
            }},
        },
    )[0]

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["next_action"] == "approve_plan"
    plan = json.loads((run_dir / "plans/figure_plan.json").read_text(encoding="utf-8"))
    assert plan["panels"] == [{
        "panel_id": "a", "bbox": [0, 0, 1, 1],
        "physical_size": [140.0, 70.0],
    }]


def test_multiple_panels_do_not_receive_ambiguous_default_layout(monkeypatch, tmp_path):
    _use_offline_runtime(monkeypatch, tmp_path)
    request = _request()
    request["auto_execute"] = False
    request["panels"] = [
        {
            "panel_id": "a", "bbox": [0, 0, 0.5, 1],
            "physical_size": [90, 112.5],
            "elements": request["panels"][0]["elements"],
        },
        {
            "panel_id": "b", "physical_size": [90, 112.5],
            "elements": [{
                "element_id": "note", "type": "text", "content": "Note",
            }],
        },
    ]
    run_dir = tmp_path / "ambiguous-panels"

    response = _rpc(monkeypatch, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": {
            "project_dir": str(tmp_path), "base_dir": str(ROOT),
            "run_dir": str(run_dir), "request": request,
        }},
    })[0]

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "paused"
    assert payload["phase"] == "planning"
    assert "panel 'b' is missing bbox" in payload["error"]


def test_long_lifecycle_operation_is_observed_without_duplicate_phase_work(
    monkeypatch, tmp_path,
):
    calls: list[str] = []

    class SlowWorker(StructuredPhaseWorker):
        def run(self, invocation):
            calls.append(invocation.phase)
            if invocation.phase == "intake":
                time.sleep(0.05)
            return super().run(invocation)

    base_factory = RuntimeContextFactory(
        config_loader=lambda _project: {"models": {}, "providers": {}},
        environ={}, cache_dir=tmp_path / "cache",
    )

    class SlowFactory:
        def create(self, project_dir, run_dir):
            return replace(
                base_factory.create(project_dir, run_dir),
                worker=SlowWorker(),
            )

    monkeypatch.setattr(server, "RuntimeContextFactory", SlowFactory)
    run_dir = tmp_path / "async-run"
    request = _request()
    request["auto_execute"] = False
    arguments = {
        "project_dir": str(tmp_path), "base_dir": str(ROOT),
        "run_dir": str(run_dir), "request": request,
        "wait_timeout": 0.005,
    }

    first = _rpc(monkeypatch, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": arguments},
    })[0]
    first_payload = json.loads(first["result"]["content"][0]["text"])
    assert first_payload["status"] == "in_progress"
    assert first_payload["operation_status"] == "running"
    assert first_payload["operation_id"]

    deadline = time.monotonic() + 10
    second_payload = first_payload
    while second_payload["status"] == "in_progress" and time.monotonic() < deadline:
        time.sleep(0.02)
        second = _rpc(monkeypatch, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(run_dir), "action": "resume",
                "operation_id": first_payload["operation_id"],
                "wait_timeout": 0.005,
            }},
        })[0]
        second_payload = json.loads(second["result"]["content"][0]["text"])
    assert second_payload["status"] == "paused"
    assert second_payload["next_action"] == "approve_plan"
    assert calls.count("intake") == 1
    assert calls.count("planning") == 1
    operation = json.loads((run_dir / "plans/phase_operation.json").read_text(encoding="utf-8"))
    assert operation["operation_id"] == first_payload["operation_id"]
    assert operation["status"] == "completed"

    repeated = _rpc(monkeypatch, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": {
            "project_dir": str(tmp_path), "base_dir": str(ROOT),
            "run_dir": str(run_dir), "action": "resume",
            "operation_id": first_payload["operation_id"],
        }},
    })[0]
    repeated_payload = json.loads(repeated["result"]["content"][0]["text"])
    assert repeated_payload == second_payload
    assert calls.count("intake") == 1
    assert calls.count("planning") == 1


def test_background_lifecycle_operation_can_be_cancelled_explicitly(
    monkeypatch, tmp_path,
):
    class CancellableWorker(StructuredPhaseWorker):
        def run(self, invocation):
            if invocation.phase == "intake":
                cancelled, _progress = server._CALL_CONTROL.get()
                while not cancelled.wait(0.01):
                    pass
                raise RuntimeError("cancelled by user")
            return super().run(invocation)

    base_factory = RuntimeContextFactory(
        config_loader=lambda _project: {"models": {}, "providers": {}},
        environ={}, cache_dir=tmp_path / "cache",
    )

    class CancellableFactory:
        def create(self, project_dir, run_dir):
            return replace(
                base_factory.create(project_dir, run_dir),
                worker=CancellableWorker(),
            )

    monkeypatch.setattr(server, "RuntimeContextFactory", CancellableFactory)
    run_dir = tmp_path / "cancel-run"
    request = _request()
    request["auto_execute"] = False
    first = _rpc(monkeypatch, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": {
            "project_dir": str(tmp_path), "run_dir": str(run_dir),
            "base_dir": str(ROOT), "request": request, "wait_timeout": 0,
        }},
    })[0]
    operation_id = json.loads(first["result"]["content"][0]["text"])["operation_id"]

    cancelled = _rpc(monkeypatch, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": {
            "run_dir": str(run_dir),
            "action": {"action": "cancel_operation", "operation_id": operation_id,
                       "reason": "Stop this local test"},
        }},
    })[0]
    cancelled_payload = json.loads(cancelled["result"]["content"][0]["text"])
    assert cancelled_payload["operation_status"] == "cancellation_requested"

    deadline = time.monotonic() + 2
    final_payload = cancelled_payload
    while final_payload["status"] == "in_progress" and time.monotonic() < deadline:
        time.sleep(0.02)
        response = _rpc(monkeypatch, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "run_dir": str(run_dir), "operation_id": operation_id,
            }},
        })[0]
        final_payload = json.loads(response["result"]["content"][0]["text"])
    assert final_payload["status"] == "paused"
    assert final_payload["operation_status"] == "cancelled"


def test_orphaned_phase_operation_is_not_resubmitted(monkeypatch, tmp_path):
    run_dir = tmp_path / "orphaned-run"
    store = RunStore(run_dir)
    store.ensure_structure()
    store.commit_json("plans/phase_operation.json", {
        "schema_version": "1.0",
        "operation_id": "orphaned-operation",
        "phase": "planning",
        "status": "running",
        "owner_pid": 99999999,
        "created_at": "2026-09-08T00:00:00+00:00",
        "updated_at": "2026-09-08T00:00:00+00:00",
        "provider_invocation_id": "provider-operation",
        "result": None,
        "error": None,
    }, schema="phase-operation.schema.json")

    class MustNotStart:
        def create(self, *_args):
            raise AssertionError("orphaned operation must not be resubmitted")

    monkeypatch.setattr(server, "RuntimeContextFactory", MustNotStart)
    response = _rpc(monkeypatch, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": {
            "run_dir": str(run_dir), "action": "resume",
        }},
    })[0]

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "paused"
    assert payload["operation_status"] == "remote_outcome_unknown"
    assert payload["next_action"] is None
    assert "Do not resubmit automatically" in payload["recovery"]


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
    _use_offline_runtime(monkeypatch, tmp_path)
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


def test_json_rpc_covers_clarification_and_plan_approval(monkeypatch, tmp_path):
    _use_offline_runtime(monkeypatch, tmp_path)
    clarification_request = _request()
    clarification_request.update({
        "export_target": None,
        "figure_width_cm": None,
        "language": None,
        "style": None,
    })
    clarification_run = tmp_path / "clarification-run"
    approval_request = _request()
    approval_request["auto_execute"] = False
    approval_run = tmp_path / "approval-run"
    responses = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(clarification_run), "request": clarification_request,
            }},
        },
        {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(clarification_run),
                "action": {"action": "submit_clarifications", "answers": {
                    "export_target": "general", "figure_width_cm": 14.0,
                    "language": "en", "style": "default",
                }},
            }},
        },
        {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(approval_run), "request": approval_request,
            }},
        },
        {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(approval_run), "action": "approve_plan",
            }},
        },
        {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(approval_run), "action": "resume",
            }},
        },
    )
    payloads = [
        json.loads(response["result"]["content"][0]["text"])
        for response in responses
    ]
    assert payloads[0]["next_action"] == "submit_clarifications"
    assert payloads[1]["status"] == "completed"
    assert payloads[2]["next_action"] == "approve_plan"
    assert payloads[3]["status"] == "completed"
    assert payloads[4]["status"] == "completed"


def test_json_rpc_covers_style_anchor_approval_without_repeating_paid_generation(
    monkeypatch, tmp_path
):
    _use_offline_runtime(monkeypatch, tmp_path)
    request = _request()
    request["panels"] = [
        {
            "panel_id": f"panel-{index}",
            "bbox": [index / 3, 0, 1 / 3, 1],
            "physical_size": [60, 112.5],
            "elements": [{
                "element_id": f"asset-{index}",
                "type": "image_asset",
                "prompt": f"asset {index}",
            }],
        }
        for index in range(3)
    ]
    run_dir = tmp_path / "style-run"
    responses = _rpc(
        monkeypatch,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "run_dir": str(run_dir),
                "base_dir": str(ROOT), "request": request,
            }},
        },
        {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "run_dir": str(run_dir),
                "base_dir": str(ROOT), "action": "approve_style_anchor",
                "wait_timeout": 0,
            }},
        },
    )
    assert all("result" in item for item in responses), responses
    payloads = [json.loads(item["result"]["content"][0]["text"]) for item in responses]
    assert payloads[0]["next_action"] == "approve_style_anchor"
    completed = payloads[1]
    assert completed["status"] == "in_progress"
    deadline = time.monotonic() + 10
    while completed["status"] == "in_progress" and time.monotonic() < deadline:
        time.sleep(0.02)
        response = _rpc(monkeypatch, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "run_dir": str(run_dir),
                "base_dir": str(ROOT), "operation_id": completed["operation_id"],
                "wait_timeout": 0.1,
            }},
        })[0]
        completed = json.loads(response["result"]["content"][0]["text"])
    assert completed["status"] == "completed"
    assert RunState.load(run_dir / "run_state.json").calls_used("generation") == 3


def test_json_rpc_covers_repair_and_force_export(monkeypatch, tmp_path):
    _use_offline_runtime(monkeypatch, tmp_path)
    broken = _request()
    broken["panels"][0]["elements"][0]["plot_spec"] = str(
        FIXTURES / "missing.json"
    )
    repair_run = tmp_path / "repair-run"
    force_run = tmp_path / "force-run"
    messages = []
    for message_id, run_dir in ((1, repair_run), (3, force_run)):
        messages.append({
            "jsonrpc": "2.0", "id": message_id, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(run_dir), "request": broken,
            }},
        })
        action = (
            {"action": "apply_repair", "repairs": [{
                "asset_id": "curve", "route": "python",
                "plot_spec": str(FIXTURES / "plot_spec_line.json"),
            }]}
            if run_dir == repair_run
            else {"action": "force_export", "reason": "explicit test override"}
        )
        messages.append({
            "jsonrpc": "2.0", "id": message_id + 1, "method": "tools/call",
            "params": {"name": "advance_figure_workflow", "arguments": {
                "project_dir": str(tmp_path), "base_dir": str(ROOT),
                "run_dir": str(run_dir), "action": action,
            }},
        })
    responses = _rpc(monkeypatch, *messages)
    assert all("result" in item for item in responses), responses
    payloads = [json.loads(item["result"]["content"][0]["text"]) for item in responses]
    assert payloads[0]["next_action"] == "repair_required"
    assert payloads[1]["status"] == "completed"
    assert payloads[2]["next_action"] == "repair_required"
    assert payloads[3]["next_action"] == "repair_required"
    assert not (force_run / "assembly" / "figure.png").exists()
    assert not (force_run / "plans" / "export_result.json").exists()


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


def test_runtime_context_construction_errors_use_the_safe_protocol_path(
    monkeypatch, tmp_path
):
    def broken_config(_project):
        raise RuntimeError("context construction leaked context-secret")

    factory = RuntimeContextFactory(
        config_loader=broken_config,
        environ={"OPENAI_API_KEY": "context-secret"},
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(server, "RuntimeContextFactory", lambda: factory)
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

    assert "context-secret" not in response["error"]["message"]
    assert "***REDACTED***" in response["error"]["message"]


def test_invalid_repair_response_is_schema_valid_pause_and_can_resume(monkeypatch, tmp_path):
    from figure_tools.phase_workers import StructuredPhaseWorker

    _use_offline_runtime(monkeypatch, tmp_path)
    original = StructuredPhaseWorker.run
    reviews = []

    def review_once_invalid(self, invocation):
        if invocation.phase == "review_and_repair":
            reviews.append(invocation)
            if len(reviews) == 1:
                return {"kind": "repair_plan", "artifact": {}}
        return original(self, invocation)

    monkeypatch.setattr(StructuredPhaseWorker, "run", review_once_invalid)
    run_dir = tmp_path / "review-run"
    responses = _rpc(monkeypatch, *[{
        "jsonrpc": "2.0", "id": i, "method": "tools/call",
        "params": {"name": "advance_figure_workflow", "arguments": {
            "project_dir": str(tmp_path), "base_dir": str(ROOT),
            "run_dir": str(run_dir), **args,
        }},
    } for i, args in enumerate([{"request": _request()}, {"action": "resume"}], 1)])
    assert all("result" in item for item in responses), responses
    paused, resumed = [json.loads(item["result"]["content"][0]["text"]) for item in responses]
    assert paused["next_action"] == "review_failed"
    assert "repairs" in paused["error"] and "status" in paused["error"]
    assert resumed["status"] == "completed"
    assert len(reviews) == 2
    assert not (run_dir / "validation" / "review_error.json").exists()
