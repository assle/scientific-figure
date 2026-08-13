"""MCP server exposing the 14 stable capability tools (plan section 8).

Tool handlers wrap the deterministic engines and the Ark client. The stdio
JSON-RPC loop lets OpenCode discover and invoke the tools. When Ark credentials
are present in the environment (ARK_API_KEY + role model IDs), real paid calls
are made under a run budget; otherwise a mock transport is used (safe default).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from figure_tools.ark.client import ArkClient
from figure_tools.ark.transport import MockArkTransport
from figure_tools.assembly.compositor import compose_assets
from figure_tools.config import initialize_project
from figure_tools.export.exporters import export_pptx
from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.planning.planner import create_figure_plan
from figure_tools.validation.final_checks import validate_assembled_figure
from figure_tools.validation.plot_checks import validate_plot_data
from figure_tools.vector.latex import latex_to_svg
from figure_tools.vector.primitives import SvgCanvas
from figure_tools.vector.svg_normalize import normalize_svg_bytes
from figure_tools.vector.wireframe import generate_wireframe

_CACHE_DIR = Path(tempfile.gettempdir()) / "scientific-figure-cache"
# Default per-run paid-call budget (plan section 12).
_DEFAULT_BUDGET = {
    "reference_analysis": 1, "generation": 5, "edits": 2,
    "validations": 5, "final_validation": 1,
}


def _models_from_env() -> dict[str, dict] | None:
    """Read the four fixed model/Endpoint IDs from the environment (user-local
    private config, plan section 5). Returns None if not all are set."""
    roles = {
        "image_generate": "ARK_IMAGE_GENERATE",
        "image_edit": "ARK_IMAGE_EDIT",
        "vision_analyze": "ARK_VISION_ANALYZE",
        "vision_validate": "ARK_VISION_VALIDATE",
    }
    models = {role: {"model": os.environ[var]} for role, var in roles.items()
              if os.environ.get(var)}
    if len(models) != len(roles):
        return None
    return models


def _client(output_dir: str | Path | None = None) -> ArkClient:
    from figure_tools.state import Cache, RunState

    models = _models_from_env()
    if models is not None and os.environ.get("ARK_API_KEY"):
        # Real Ark (Phase 7). Plan routing is handled by RealArkTransport.
        from figure_tools.ark.real_transport import RealArkTransport

        transport = RealArkTransport()
        api_key = os.environ["ARK_API_KEY"]
        budget = _DEFAULT_BUDGET
    else:
        transport = MockArkTransport()
        models = models or {
            "image_generate": {"model": "mock"},
            "image_edit": {"model": "mock"},
            "vision_analyze": {"model": "mock"},
            "vision_validate": {"model": "mock"},
        }
        api_key = None
        budget = {}

    return ArkClient(
        models, transport, api_key=api_key,
        state=RunState("mcp", budget=budget),
        cache=Cache(_CACHE_DIR), output_dir=Path(output_dir) if output_dir else None,
    )


# --- handlers ---------------------------------------------------------------
def _h_initialize_figure_project(args):
    cfg = initialize_project(args["project_dir"])
    return {"config": cfg}


def _h_analyze_reference_figure(args):
    return _client().analyze_reference_figure(args["image_path"], prompt=args.get("prompt"))


def _h_create_figure_plan(args):
    return {"figure_plan": create_figure_plan(args["request"])}


def _h_create_layout_wireframe(args):
    return {"svg": generate_wireframe(args["figure_plan"])}


def _h_generate_image_asset(args):
    meta = _client().generate_image_asset(args["prompt"], {}, output_path=args["output_path"])
    return {"meta": meta}


def _h_edit_image_asset(args):
    meta = _client().edit_image_asset(args["parent_path"], args["prompt"], {},
                                      output_path=args["output_path"])
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
    report = _client().validate_image_asset(
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
    return validate_assembled_figure(
        args["figure_plan"], args["asset_manifest"], args["composed_image_path"],
        physical_size_mm=tuple(args["physical_size_mm"]),
        run_id=args.get("run_id"),
        ark_client=_client())


def _h_export_figure(args):
    import shutil

    source_dir = Path(args["source_dir"])
    output_dir = Path(args["output_dir"])
    force_export = args.get("force_export", False)

    # Validation gate (spec 0001, improvement 3): refuse export if no
    # validation report exists or if it contains blocking errors.
    validation_report_path = source_dir.parent / "validation" / "validation_report.json"
    if not force_export:
        if not validation_report_path.exists():
            return {"files": {}, "export_blocked_reason": (
                f"no validation report found at {validation_report_path}; "
                "run validation before export or use force_export=True")}
        import json as _json

        report = _json.loads(validation_report_path.read_text(encoding="utf-8"))
        if report.get("summary", {}).get("blocking", False):
            return {"files": {}, "export_blocked_reason": (
                "validation report contains blocking errors; "
                "use force_export=True to override")}

    output_dir.mkdir(parents=True, exist_ok=True)
    formats = args.get("formats", ["png", "svg", "pdf"])
    files = {}
    for ext in formats:
        src = source_dir / f"figure.{ext}"
        if src.exists():
            dst = output_dir / f"figure.{ext}"
            shutil.copyfile(src, dst)
            files[ext] = str(dst)
    if args.get("include_pptx"):
        export_pptx(args.get("placements", []), output_dir / "figure.pptx",
                    tuple(args["canvas_mm"]), title=args.get("title"))
        files["pptx"] = str(output_dir / "figure.pptx")
    return {"files": files}


def _h_resume_figure_run(args):
    from figure_tools.state import RunState

    state_path = Path(args["run_dir"]) / "run_state.json"
    if state_path.exists():
        return {"run_state": RunState.load(state_path).to_dict()}
    return {"run_state": None}


REQUIRED_TOOLS = [
    "initialize_figure_project",
    "analyze_reference_figure",
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
]

_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "initialize_figure_project": _h_initialize_figure_project,
    "analyze_reference_figure": _h_analyze_reference_figure,
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
}

_DESCRIPTIONS = {
    "initialize_figure_project": "Create non-secret project config (.scientific-figure/).",
    "analyze_reference_figure": "Analyze a reference figure via the Ark vision model.",
    "create_figure_plan": "Build a versioned figure plan from a structured request.",
    "create_layout_wireframe": "Render a no-cost SVG layout wireframe from a plan.",
    "generate_image_asset": "Generate one isolated transparent asset via the Ark image model.",
    "edit_image_asset": "Edit an existing asset via reference-image editing.",
    "render_scientific_plot": "Render a reproducible data plot from a plot spec.",
    "render_vector_element": "Render an SVG label or LaTeX equation.",
    "validate_image_asset": "Two-layer validation of an image asset.",
    "validate_plot_data": "Deterministic source-to-render data validation.",
    "assemble_figure": "Compose panel assets into a final figure.",
    "validate_assembled_figure": "Final assembled-figure validation.",
    "export_figure": "Export final PNG/SVG/PDF (optional PPTX).",
    "resume_figure_run": "Load run state for resume.",
}

TOOL_REGISTRY = {
    name: {"handler": _HANDLERS[name], "description": _DESCRIPTIONS[name],
           "input_schema": {"type": "object"}}
    for name in REQUIRED_TOOLS
}


def dispatch(name: str, arguments: dict[str, Any]) -> Any:
    return TOOL_REGISTRY[name]["handler"](arguments)


def _tool_list() -> list[dict]:
    return [
        {"name": name, "description": TOOL_REGISTRY[name]["description"],
         "inputSchema": TOOL_REGISTRY[name]["input_schema"]}
        for name in REQUIRED_TOOLS
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
                      "serverInfo": {"name": "scientific-figure", "version": "0.1.0"}}
        elif method == "tools/list":
            result = {"tools": _tool_list()}
        elif method == "tools/call":
            name = msg["params"]["name"]
            arguments = msg["params"].get("arguments", {})
            try:
                data = dispatch(name, arguments)
                result = {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
            except Exception as e:  # noqa: BLE001
                sys.stdout.write(json.dumps(
                    {"jsonrpc": "2.0", "id": mid,
                     "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}) + "\n")
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
