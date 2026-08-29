"""MCP server exposing the stable capability tools and lifecycle orchestrator.

Tool handlers wrap the deterministic engines and the provider client. The stdio
JSON-RPC loop lets supported Calling Agents discover and invoke the tools. When
configured provider credentials resolve from the system store or environment,
real paid calls are made under a run budget; otherwise a mock transport is used
(safe default).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from figure_tools import __version__
from figure_tools.providers.client import ProviderClient
from figure_tools.orchestrator import FigureOrchestrator
from figure_tools.providers.auth import (
    SecretRedactor,
    default_secret_store,
    resolve_provider_credentials,
    sanitize_error,
)
from figure_tools.providers.generic_transport import ProviderRouter
from figure_tools.providers.transport import MockProviderTransport, model_config_for_role
from figure_tools.phase_workers import ProviderPhaseWorker, StructuredPhaseWorker
from figure_tools.assembly.compositor import compose_assets
from figure_tools.config import (
    configured_models,
    configured_providers,
    initialize_project,
    load_config,
)
from figure_tools.export.publish import export_figure
from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.planning.planner import collect_required_clarifications, create_figure_plan
from figure_tools.validation.engine import FigureQAEngine
from figure_tools.validation.models import AssembledFigure
from figure_tools.validation.plot_checks import validate_plot_data
from figure_tools.vector.latex import latex_to_svg
from figure_tools.vector.primitives import SvgCanvas
from figure_tools.vector.svg_normalize import normalize_svg_bytes
from figure_tools.vector.wireframe import generate_wireframe

_CACHE_DIR = Path(tempfile.gettempdir()) / "scientific-figure-cache"
# Default per-run paid-call budget (plan section 12).
_DEFAULT_BUDGET = {
    "phase_reasoning": 10,
    "reference_analysis": 1, "generation": 5, "edits": 2,
    "validations": 5, "final_validation": 1,
}


def _project_dir_for_paths(*values: str | Path | None) -> Path | None:
    explicit_dir = os.environ.get("SCIENTIFIC_FIGURE_PROJECT_DIR")
    if explicit_dir:
        return Path(explicit_dir)
    for value in values:
        if not value:
            continue
        path = Path(value)
        if not path.is_dir():
            path = path.parent
        for candidate in (path, *path.parents):
            if (candidate / ".scientific-figure").is_dir():
                return candidate
    return None


def _client(output_dir: str | Path | None = None,
            project_dir: str | Path | None = None) -> ProviderClient:
    from figure_tools.state import Cache, RunState

    resolved_project_dir = project_dir or _project_dir_for_paths(output_dir)
    models = configured_models(resolved_project_dir)
    providers = configured_providers(resolved_project_dir)
    credentials = resolve_provider_credentials(
        providers, secret_store=default_secret_store(),
    )
    provider_names = {
        name
        for model_cfg in (models or {}).values()
        if (name := model_cfg.get("provider"))
    }
    live_credentials = {
        name: credential for name, credential in credentials.items()
        if name in provider_names
    }
    has_live_provider = bool(live_credentials)
    if models and has_live_provider:
        try:
            transport = ProviderRouter(
                models, providers, credentials=live_credentials,
            )
        except TypeError as exc:
            # Keep third-party/test adapters written against the pre-injection
            # two-argument constructor working while the built-in router uses
            # the explicit credential map.
            if "credentials" not in str(exc):
                raise
            transport = ProviderRouter(models, providers)
        api_keys = [credential.value for credential in live_credentials.values()]
        api_key = api_keys[0] if api_keys else None
        budget = dict(_DEFAULT_BUDGET)
        if "image_edit" not in models:
            budget.pop("edits", None)
    else:
        transport = MockProviderTransport()
        models = models or {
            "image_generate": {"model": "mock"},
            "image_edit": {"model": "mock"},
            "vision_analyze": {"model": "mock"},
            "vision_validate": {"model": "mock"},
        }
        api_key = None
        api_keys = []
        budget = {}

    return ProviderClient(
        models, transport, api_key=api_key, api_keys=api_keys,
        redactor=SecretRedactor(api_keys),
        state=RunState("mcp", budget=budget),
        cache=Cache(_CACHE_DIR), output_dir=Path(output_dir) if output_dir else None,
    )


# --- handlers ---------------------------------------------------------------
def _h_initialize_figure_project(args):
    cfg = initialize_project(args["project_dir"])
    return {"config": cfg}


def _h_analyze_reference_figure(args):
    project_dir = args.get("project_dir") or _project_dir_for_paths(args["image_path"])
    return _client(project_dir=project_dir).analyze_reference_figure(
        args["image_path"], prompt=args.get("prompt"))


def _h_create_figure_plan(args):
    return {"figure_plan": create_figure_plan(args["request"])}


def _h_check_figure_requirements(args):
    clarifications = collect_required_clarifications(args["request"])
    return {"blocked": bool(clarifications), "requirements": clarifications}


def _h_create_layout_wireframe(args):
    return {"svg": generate_wireframe(args["figure_plan"])}


def _h_generate_image_asset(args):
    project_dir = args.get("project_dir") or _project_dir_for_paths(args["output_path"])
    meta = _client(output_dir=Path(args["output_path"]).parent,
                   project_dir=project_dir).generate_image_asset(
        args["prompt"], {}, output_path=args["output_path"])
    return {"meta": meta}


def _h_edit_image_asset(args):
    project_dir = args.get("project_dir") or _project_dir_for_paths(
        args["parent_path"], args["output_path"])
    meta = _client(output_dir=Path(args["output_path"]).parent,
                   project_dir=project_dir).edit_image_asset(
        args["parent_path"], args["prompt"], {}, output_path=args["output_path"])
    return {"meta": meta}


def _h_render_scientific_plot(args):
    spec = load_plot_spec(args["plot_spec_path"])
    out = render_plot(spec, output_dir=args["output_dir"], base_dir=args.get("base_dir", "."),
                      export_target=args.get("export_target"))
    return {"files": out["files"]}


def _h_render_vector_element(args):
    kind = args.get("kind", "label")
    content = args["content"]
    export_target = args.get("export_target", "general")
    if kind == "equation":
        return {"svg": latex_to_svg(content, export_target=export_target)}
    canvas = SvgCanvas(width=200, height=40)
    canvas.text(2, 16, content, font_size=12, fill="#000000")
    svg = normalize_svg_bytes(canvas.to_string().encode("utf-8"),
                              export_target=export_target).decode("utf-8")
    return {"svg": svg}


def _h_validate_image_asset(args):
    project_dir = args.get("project_dir") or _project_dir_for_paths(args["image_path"])
    report = _client(project_dir=project_dir).validate_image_asset(
        args["image_path"],
        physical_size_mm=tuple(args["physical_size_mm"]) if args.get("physical_size_mm") else None)
    return report


def _h_validate_plot_data(args):
    spec = load_plot_spec(args["plot_spec_path"])
    base_dir = Path(args.get("base_dir", "."))
    source = load_source_data(base_dir / spec.source_data["path"])
    used = build_data_used(spec, source)
    return validate_plot_data(spec, source_df=source, data_used_df=used,
                              source_path=base_dir / spec.source_data["path"])


def _h_assemble_figure(args):
    out = compose_assets(args["placements"], output_dir=args["output_dir"],
                         canvas_mm=tuple(args["canvas_mm"]),
                         dpi=args.get("dpi", 300),
                         text_placements=args.get("text_placements"),
                         export_target=args.get("export_target"))
    return {"files": out["files"]}


def _h_validate_assembled_figure(args):
    project_dir = args.get("project_dir") or _project_dir_for_paths(
        args["composed_image_path"], args.get("layout_manifest_path"))
    return FigureQAEngine(config=args.get("qa_config") or {},
                          provider_client=_client(
                              output_dir=Path(args["composed_image_path"]).parent,
                              project_dir=project_dir)).validate_final(
        AssembledFigure(
            figure_plan=args["figure_plan"],
            asset_manifest=args["asset_manifest"],
            image_path=args["composed_image_path"],
            layout_manifest_path=args.get("layout_manifest_path"),
            physical_size_mm=tuple(args["physical_size_mm"]),
            asset_placements=args.get("asset_placements"),
        ),
        run_id=args.get("run_id"),
    )


def _h_export_figure(args):
    import json as _json

    source_dir = Path(args["source_dir"])
    output_dir = Path(args["output_dir"])
    validation_report_path = source_dir.parent / "validation" / "validation_report.json"
    if validation_report_path.exists():
        report = _json.loads(validation_report_path.read_text(encoding="utf-8"))
        validation_reports = [report]
    else:
        validation_reports = []
    return export_figure(
        validation_reports,
        source_dir=source_dir,
        output_dir=output_dir,
        force_export=args.get("force_export", False),
        formats=args.get("formats", ["png", "svg", "pdf"]),
    )


def _h_resume_figure_run(args):
    from figure_tools.state import RunState

    state_path = Path(args["run_dir"]) / "run_state.json"
    if state_path.exists():
        return {"run_state": RunState.load(state_path).to_dict()}
    return {"run_state": None}


def _h_advance_figure_workflow(args):
    """Run the high-level lifecycle seam and keep low-level tools internal."""
    from figure_tools.state import RunDirectory, RunState

    run_dir = Path(args["run_dir"])
    RunDirectory.ensure_structure(run_dir)
    state_path = run_dir / "run_state.json"
    state = RunState.load(state_path) if state_path.exists() else RunState(
        run_id=run_dir.name, budget=dict(_DEFAULT_BUDGET),
    )
    client = _client(
        output_dir=run_dir,
        project_dir=args.get("project_dir") or _project_dir_for_paths(run_dir),
    )
    # _client builds the configured transport and redactor; the orchestrator
    # owns the durable per-run state used by that client.
    client.state = state
    worker = (
        ProviderPhaseWorker(client)
        if model_config_for_role(client.models, "phase_reasoning") is not None
        else StructuredPhaseWorker()
    )
    orchestrator = FigureOrchestrator(
        request=args.get("request"),
        config=load_config(args.get("project_dir") or _project_dir_for_paths(run_dir) or "."),
        run_dir=run_dir,
        provider_client=client,
        state=state,
        base_dir=args.get("base_dir", "."),
        compose_dpi=int(args.get("dpi", 300)),
        worker=worker,
    )
    return orchestrator.advance(args.get("action"))


REQUIRED_TOOLS = [
    "initialize_figure_project",
    "analyze_reference_figure",
    "check_figure_requirements",
    "create_figure_plan",
    "create_layout_wireframe",
    "generate_image_asset",
    "edit_image_asset",
    "render_scientific_plot",
    "render_vector_element",
    "validate_image_asset",
    "validate_plot_data",
    "assemble_figure",
    "validate_assembled_figure",
    "export_figure",
    "resume_figure_run",
    "advance_figure_workflow",
]

PUBLIC_TOOLS = ["initialize_figure_project", "advance_figure_workflow"]

_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "initialize_figure_project": _h_initialize_figure_project,
    "analyze_reference_figure": _h_analyze_reference_figure,
    "check_figure_requirements": _h_check_figure_requirements,
    "create_figure_plan": _h_create_figure_plan,
    "create_layout_wireframe": _h_create_layout_wireframe,
    "generate_image_asset": _h_generate_image_asset,
    "edit_image_asset": _h_edit_image_asset,
    "render_scientific_plot": _h_render_scientific_plot,
    "render_vector_element": _h_render_vector_element,
    "validate_image_asset": _h_validate_image_asset,
    "validate_plot_data": _h_validate_plot_data,
    "assemble_figure": _h_assemble_figure,
    "validate_assembled_figure": _h_validate_assembled_figure,
    "export_figure": _h_export_figure,
    "resume_figure_run": _h_resume_figure_run,
    "advance_figure_workflow": _h_advance_figure_workflow,
}

_DESCRIPTIONS = {
    "initialize_figure_project": "Create non-secret project config (.scientific-figure/).",
    "analyze_reference_figure": "Analyze a reference figure via the configured vision model.",
    "check_figure_requirements": "Return unresolved required questions that must be answered before any generation.",
    "create_figure_plan": "Build a versioned figure plan from a structured request.",
    "create_layout_wireframe": "Render a no-cost SVG layout wireframe from a plan.",
    "generate_image_asset": "Generate one isolated transparent asset via the configured image model.",
    "edit_image_asset": (
        "Revise a generated or source-less raster asset; plots and vectors "
        "must be re-rendered from source."
    ),
    "render_scientific_plot": "Render a reproducible data plot from a plot spec.",
    "render_vector_element": "Render an SVG label or LaTeX equation.",
    "validate_image_asset": "Two-layer validation of an image asset.",
    "validate_plot_data": "Deterministic source-to-render data validation.",
    "assemble_figure": "Compose panel assets into a final figure.",
    "validate_assembled_figure": "Final assembled-figure validation.",
    "export_figure": "Export final PNG/SVG/PDF (optional PPTX).",
    "resume_figure_run": "Load run state for resume.",
    "advance_figure_workflow": (
        "Advance one figure lifecycle transition through the single orchestrator."
    ),
}

_FIGURE_REQUEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["figure_id", "panels"],
    "properties": {
        "figure_id": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "minLength": 1},
        "intent": {"type": "string"},
        "description": {"type": "string"},
        "canvas": {
            "type": "object", "additionalProperties": False,
            "required": ["aspect_ratio", "width", "height"],
            "properties": {
                "aspect_ratio": {"type": "number", "exclusiveMinimum": 0},
                "width": {"type": "number", "exclusiveMinimum": 0},
                "height": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "units": {"type": "string", "enum": ["mm", "cm", "in", "px"]},
        "panels": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["panel_id", "bbox", "physical_size", "elements"],
                "properties": {
                    "panel_id": {"type": "string", "minLength": 1},
                    "bbox": {"type": "array", "minItems": 4, "maxItems": 4,
                             "items": {"type": "number"}},
                    "physical_size": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "number", "exclusiveMinimum": 0}},
                    "elements": {
                        "type": "array",
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["element_id", "type"],
                            "properties": {
                                "element_id": {"type": "string", "minLength": 1},
                                "type": {"type": "string", "enum": [
                                    "data_plot", "image_asset", "label", "annotation",
                                    "text", "equation", "vector_element",
                                ]},
                                "plot_spec": {"type": "string", "minLength": 1},
                                "prompt": {"type": "string", "minLength": 1},
                                "content": {"type": "string", "minLength": 1},
                                "parameters": {"type": "object"},
                            },
                        },
                    },
                },
            },
        },
        "labels": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["element_id", "kind", "content"],
                "properties": {
                    "element_id": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "enum": ["label", "annotation", "equation"]},
                    "content": {"type": "string", "minLength": 1},
                    "panel_id": {"type": "string", "minLength": 1},
                },
            },
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "user_input_requirements": {"type": "array", "items": {"type": "string"}},
        "reference_figures": {"type": "array", "items": {"type": "string"}},
        "export_target": {"type": ["string", "null"], "enum": ["general", "ppt", None]},
        "figure_width_cm": {"type": ["number", "null"], "exclusiveMinimum": 0},
        "language": {"type": ["string", "null"], "enum": ["zh", "en", None]},
        "style": {"type": ["string", "object", "null"]},
        "include_pptx": {"type": "boolean"},
        "auto_execute": {"type": "boolean"},
    },
}


_WORKFLOW_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_dir"],
    "properties": {
        "run_dir": {"type": "string", "minLength": 1},
        "project_dir": {"type": "string", "minLength": 1},
        "base_dir": {"type": "string", "minLength": 1},
        "dpi": {"type": "integer", "minimum": 1},
        "request": _FIGURE_REQUEST_SCHEMA,
        "action": {
            "oneOf": [
                {"type": "string", "enum": [
                    "start", "resume", "approve_plan",
                    "approve_style_anchor",
                ]},
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "answers"],
                    "properties": {
                        "action": {"const": "submit_clarifications"},
                        "answers": {
                            "type": "object", "additionalProperties": False,
                            "minProperties": 1,
                            "properties": {
                                "export_target": {"type": "string", "enum": ["general", "ppt"]},
                                "figure_width_cm": {"type": "number", "exclusiveMinimum": 0},
                                "language": {"type": "string", "enum": ["zh", "en"]},
                                "style": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "repairs"],
                    "properties": {
                        "action": {"const": "apply_repair"},
                        "repairs": {
                            "type": "array", "minItems": 1,
                            "items": {
                                "type": "object", "additionalProperties": False,
                                "required": ["asset_id", "route"],
                                "properties": {
                                    "asset_id": {"type": "string", "minLength": 1},
                                    "route": {"type": "string", "enum": ["python", "svg", "image_edit"]},
                                    "plot_spec": {"type": "string", "minLength": 1},
                                    "content": {"type": "string", "minLength": 1},
                                    "prompt": {"type": "string", "minLength": 1},
                                },
                            },
                        },
                    },
                },
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "reason"],
                    "properties": {
                        "action": {"const": "force_export"},
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
            ],
        },
    },
}

_ARTIFACT_REFERENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "exists", "content_hash"],
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "exists": {"type": "boolean"},
        "content_hash": {"type": ["string", "null"]},
    },
}

_WORKFLOW_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phase", "status", "next_action", "artifacts"],
    "properties": {
        "phase": {"type": "string", "enum": [
            "intake", "planning", "execution", "review_and_repair", "export",
        ]},
        "status": {"type": "string", "enum": ["paused", "completed"]},
        "next_action": {"type": ["string", "null"]},
        "artifacts": {
            "type": "object",
            "additionalProperties": _ARTIFACT_REFERENCE_SCHEMA,
        },
        "clarifications": {"type": "array", "items": {"type": "object"}},
        "export_blocked_reason": {"type": ["string", "null"]},
    },
}


def _input_schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


_PATH = {"type": "string", "minLength": 1}
_OBJECT = {"type": "object"}
_TOOL_INPUT_SCHEMAS = {
    "initialize_figure_project": _input_schema(["project_dir"], {
        "project_dir": _PATH,
    }),
    "analyze_reference_figure": _input_schema(["image_path"], {
        "image_path": _PATH, "prompt": {"type": "string"},
        "project_dir": _PATH,
    }),
    "check_figure_requirements": _input_schema(["request"], {
        "request": _OBJECT,
    }),
    "create_figure_plan": _input_schema(["request"], {
        "request": _OBJECT,
    }),
    "create_layout_wireframe": _input_schema(["figure_plan"], {
        "figure_plan": _OBJECT,
    }),
    "generate_image_asset": _input_schema(["prompt", "output_path"], {
        "prompt": {"type": "string", "minLength": 1},
        "output_path": _PATH, "project_dir": _PATH,
    }),
    "edit_image_asset": _input_schema(["parent_path", "prompt", "output_path"], {
        "parent_path": _PATH, "prompt": {"type": "string", "minLength": 1},
        "output_path": _PATH, "project_dir": _PATH,
    }),
    "render_scientific_plot": _input_schema(["plot_spec_path", "output_dir"], {
        "plot_spec_path": _PATH, "output_dir": _PATH,
        "base_dir": _PATH,
        "export_target": {"type": "string", "enum": ["general", "ppt"]},
    }),
    "render_vector_element": _input_schema(["content"], {
        "content": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": ["label", "annotation", "equation", "text"]},
        "export_target": {"type": "string", "enum": ["general", "ppt"]},
    }),
    "validate_image_asset": _input_schema(["image_path"], {
        "image_path": _PATH, "physical_size_mm": {"type": "array"},
        "project_dir": _PATH,
    }),
    "validate_plot_data": _input_schema(["plot_spec_path"], {
        "plot_spec_path": _PATH, "base_dir": _PATH,
    }),
    "assemble_figure": _input_schema(["placements", "output_dir", "canvas_mm"], {
        "placements": {"type": "array"}, "output_dir": _PATH,
        "canvas_mm": {"type": "array", "minItems": 2, "maxItems": 2},
        "dpi": {"type": "integer", "minimum": 1},
        "text_placements": {"type": "array"}, "source_layouts": _OBJECT,
        "export_target": {"type": "string", "enum": ["general", "ppt"]},
    }),
    "validate_assembled_figure": _input_schema(
        ["figure_plan", "asset_manifest", "composed_image_path", "physical_size_mm"],
        {
            "figure_plan": _OBJECT, "asset_manifest": _OBJECT,
            "composed_image_path": _PATH,
            "physical_size_mm": {"type": "array", "minItems": 2, "maxItems": 2},
            "layout_manifest_path": _PATH, "asset_placements": _OBJECT,
            "qa_config": _OBJECT, "run_id": {"type": "string"},
            "project_dir": _PATH,
        },
    ),
    "export_figure": _input_schema(["source_dir", "output_dir"], {
        "source_dir": _PATH, "output_dir": _PATH,
        "force_export": {"type": "boolean"},
        "formats": {"type": "array", "items": {"type": "string"}},
    }),
    "resume_figure_run": _input_schema(["run_dir"], {
        "run_dir": _PATH,
    }),
    "advance_figure_workflow": _WORKFLOW_INPUT_SCHEMA,
}

TOOL_REGISTRY = {
    name: {"handler": _HANDLERS[name], "description": _DESCRIPTIONS[name],
           "input_schema": _TOOL_INPUT_SCHEMAS[name],
           **({"output_schema": _WORKFLOW_OUTPUT_SCHEMA}
              if name == "advance_figure_workflow" else {})}
    for name in REQUIRED_TOOLS
}


def dispatch(name: str, arguments: dict[str, Any]) -> Any:
    tool = TOOL_REGISTRY[name]
    from jsonschema import Draft202012Validator
    errors = sorted(
        Draft202012Validator(tool["input_schema"]).iter_errors(arguments),
        key=lambda error: list(error.path),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise ValueError(f"invalid arguments for {name}: {detail}")
    result = tool["handler"](arguments)
    output_schema = tool.get("output_schema")
    if output_schema is not None:
        output_errors = sorted(
            Draft202012Validator(output_schema).iter_errors(result),
            key=lambda error: list(error.path),
        )
        if output_errors:
            detail = "; ".join(error.message for error in output_errors)
            raise ValueError(f"invalid result for {name}: {detail}")
    return result


def _tool_list() -> list[dict]:
    return [
        {"name": name, "description": TOOL_REGISTRY[name]["description"],
         "inputSchema": TOOL_REGISTRY[name]["input_schema"],
         **({"outputSchema": TOOL_REGISTRY[name]["output_schema"]}
            if "output_schema" in TOOL_REGISTRY[name] else {})}
        for name in PUBLIC_TOOLS
    ]


def serve_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "scientific-figure", "version": __version__}}
        elif method == "tools/list":
            result = {"tools": _tool_list()}
        elif method == "tools/call":
            name = msg["params"]["name"]
            if name not in PUBLIC_TOOLS:
                sys.stdout.write(json.dumps(
                    {"jsonrpc": "2.0", "id": mid,
                     "error": {"code": -32601, "message": f"tool {name!r} is internal"}}) + "\n")
                sys.stdout.flush()
                continue
            arguments = msg["params"].get("arguments", {})
            try:
                data = dispatch(name, arguments)
                result = {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
            except Exception as e:  # noqa: BLE001
                # Dispatch handlers do not guess which exceptions are safe to
                # retry. The protocol boundary performs one consistent,
                # multi-credential redaction pass before returning details.
                try:
                    providers = configured_providers(
                        _project_dir_for_paths(arguments.get("project_dir"))
                    )
                    secrets = [
                        item.value for item in resolve_provider_credentials(
                            providers, secret_store=default_secret_store(),
                        ).values()
                    ]
                except Exception:  # noqa: BLE001
                    secrets = []
                sys.stdout.write(json.dumps(
                    {"jsonrpc": "2.0", "id": mid,
                     "error": {"code": -32603, "message": sanitize_error(e, secrets)}}) + "\n")
                sys.stdout.flush()
                continue
        else:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": mid,
                 "error": {"code": -32601, "message": f"unknown method {method}"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
