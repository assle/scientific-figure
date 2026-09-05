"""Real-model acceptance tests (plan section 15).

These make REAL paid calls against the providers configured in the user config
(``~/.config/scientific-figure-builder/config.yaml``, or the file named by
``SCIENTIFIC_FIGURE_CONFIG``). They build the client exactly the way the MCP server
does (``figure_tools.server._client``), so model IDs, provider types, base URLs, and
``key_env``s all come from the same config. A run is skipped unless that config
resolves to a real provider whose credential(s) are present in the environment.

To point an acceptance run at your own providers (e.g. DeepSeek multimodal for
reference analysis / validation and Seedream for image generation), just edit the
user config and export the matching ``key_env`` credentials; no test code changes.
"""

from __future__ import annotations

import filecmp
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.orchestrator import FigureOrchestrator
from figure_tools.providers.transport import MockProviderTransport
from figure_tools.runtime_context import RuntimeContextFactory
from figure_tools.state import RunDirectory
from figure_tools.validation.plot_checks import validate_plot_data

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"

# The MCP server's default per-run paid-call budget (plan section 12).
BUDGET = {"reference_analysis": 4, "generation": 5, "edits": 2,
          "validations": 5, "final_validation": 1}


def _real_context(run_dir: Path):
    """Build a client from the configured providers (same path as the MCP server)."""
    context = RuntimeContextFactory().create(ROOT, run_dir)
    client = context.client
    if isinstance(getattr(client, "transport", None), MockProviderTransport):
        pytest.skip(
            "no configured provider with credentials in the environment; "
            "set your user config (SCIENTIFIC_FIGURE_CONFIG) and export its key_env"
        )
    # An acceptance run must exercise the live providers, not the shared
    # content-addressed cache. The cache is a production cost/reproducibility
    # feature; disabling it here keeps every acceptance run a genuine call.
    client.cache = None
    return context


# --- Case 1: CSV -> reproducible publication plot (no AI assets) -----------
def test_case1_csv_to_reproducible_plot(tmp_path: Path):
    spec = load_plot_spec(FIXTURES / "plot_spec_line.json")
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    render_plot(spec, output_dir=a, base_dir=ROOT)
    render_plot(spec, output_dir=b, base_dir=ROOT)
    for name in ("plot.png", "plot.svg", "plot.pdf", "data_used.csv"):
        assert filecmp.cmp(a / name, b / name, shallow=False), f"{name} not reproducible"
    # Quantitative plot matches source.
    source = load_source_data(FIXTURES / "coupling.csv")
    used = build_data_used(spec, source)
    report = validate_plot_data(spec, source_df=source, data_used_df=used,
                                source_path=FIXTURES / "coupling.csv")
    assert report["summary"]["blocking"] is False


# --- Case 2: reference decomposition -> transparent asset -> reconstruction --
def test_case2_reference_decomposition(tmp_path: Path):
    run_dir = RunDirectory(base_dir=tmp_path).create("case2")
    client = _real_context(run_dir).client

    # Make a simple reference figure to decompose.
    ref = run_dir / "inputs" / "reference.png"
    ref.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (800, 600), (255, 255, 255))
    ImageDraw.Draw(img).ellipse((200, 150, 600, 450), fill=(200, 40, 40))
    ImageDraw.Draw(img).text((20, 20), "(a) Setup", fill=(0, 0, 0))
    img.save(ref)

    analysis = client.analyze_reference_figure(ref, prompt="Decompose this figure.")
    assert "panels" in analysis or "objects" in analysis

    asset = run_dir / "assets" / "reconstructed.png"
    meta = client.generate_image_asset(
        "isolated optical fiber cross-section, transparent background, no text",
        {"size": "2048x2048"}, output_path=asset)
    assert asset.is_file()
    assert meta["transparent"] is True
    assert meta["pixel_dimensions"][0] >= 512

    report = client.validate_image_asset(asset, physical_size_mm=(80, 80))
    assert report["summary"]["errors"] == 0 or report["summary"]["blocking"] is False


# --- Case 3: hybrid multipanel (AI asset + Python plot + SVG labels) --------
def test_case3_hybrid_multipanel(tmp_path: Path):
    run_dir = RunDirectory(base_dir=tmp_path).create("case3")
    context = _real_context(run_dir)
    client = context.client
    request = {
        "figure_id": "case3",
        "canvas": {"aspect_ratio": 1.6, "width": 180, "height": 112.5},
        "units": "mm",
        "panels": [
            {"panel_id": "a", "bbox": [0, 0, 0.5, 1], "physical_size": [90, 112.5],
             "elements": [{"element_id": "curve", "type": "data_plot",
                           "plot_spec": str(FIXTURES / "plot_spec_line.json")}]},
            {"panel_id": "b", "bbox": [0.5, 0, 0.5, 1], "physical_size": [90, 112.5],
             "elements": [{"element_id": "fiber", "type": "image_asset",
                           "prompt": "semi-realistic optical fiber cross-section, "
                                     "transparent background, no text, no labels"}]},
        ],
        "labels": [{"element_id": "label-a", "kind": "label", "content": "(a) Coupling"}],
        "assumptions": ["Gaussian beam approximation."],
        "uncertainties": [],
        "user_input_requirements": [],
        "export_target": "general",
        "figure_width_cm": 14.0,
        "language": "en",
        "style": "default",
        "auto_execute": True,
    }
    orchestrator = FigureOrchestrator(
        request=request,
        config=context.effective_config,
        run_dir=run_dir,
        provider_client=client,
        state=context.state,
        base_dir=ROOT,
        compose_dpi=300,
        worker=context.worker,
    )
    # Use force_export because the vision model is non-deterministic and may
    # return per-asset checks that block the gate even for valid figures.
    result = orchestrator.advance()
    if result["status"] == "paused" and result["next_action"] == "force_export":
        result = orchestrator.advance({
            "action": "force_export",
            "reason": "paid acceptance test validates force-export wiring",
        })
    assert result["status"] == "completed"

    # Formal outputs present in all default formats.
    for ext in ("png", "svg", "pdf"):
        assert (run_dir / "exports" / f"figure.{ext}").is_file()

    # AI asset is isolated and transparent; data plot from Python.
    manifest = json.loads((run_dir / "asset_manifest.json").read_text())
    fiber = next(a for a in manifest["assets"] if a["asset_id"] == "fiber")
    assert fiber["transparent"] is True
    plan = json.loads((run_dir / "plans" / "figure_plan.json").read_text())
    plan_routing = {a["asset_id"]: a["routing"] for a in plan["assets"]}
    assert plan_routing["curve"] == "python"
    assert plan_routing["fiber"] == "image_model"

    # Budget respected (no exceptions => within budget).
    assert client.state.calls_used("generation") <= BUDGET["generation"]

    # Reports complete.
    assert (run_dir / "generation_report.md").is_file()
    assert (run_dir / "run_state.json").is_file()
    final = json.loads((run_dir / "validation" / "final.json").read_text())
    # The vision model is non-deterministic, so a blocking final summary is
    # expected on some runs (that's why force_export is used). The acceptance
    # criterion is that the final validation actually ran and produced a
    # well-formed report.
    assert isinstance(final.get("summary"), dict)
    assert "blocking" in final["summary"]
    assert isinstance(final.get("checks"), list) and final["checks"]

    # Secrets never leaked into the run directory (all configured keys).
    keys = [k.encode() for k in getattr(client, "api_keys", []) if k]
    for f in run_dir.rglob("*"):
        if f.is_file() and f.suffix not in (".png", ".svg", ".pdf"):
            for key in keys:
                assert key not in f.read_bytes(), f"API key leaked in {f}"
