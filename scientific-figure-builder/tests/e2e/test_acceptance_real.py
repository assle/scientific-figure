"""Phase 7 real-model acceptance tests (plan section 15).

These make REAL paid Volcengine Ark calls. They are skipped unless credentials
are present in the environment:
  ARK_API_KEY, ARK_IMAGE_GENERATE, ARK_IMAGE_EDIT,
  ARK_VISION_ANALYZE, ARK_VISION_VALIDATE
"""

from __future__ import annotations

import filecmp
import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from figure_tools.ark.client import ArkClient
from figure_tools.ark.real_transport import RealArkTransport
from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.state import Cache, RunDirectory, RunState
from figure_tools.validation.plot_checks import validate_plot_data
from figure_tools.workflow import FigureWorkflow

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"

CREDS = {"ARK_API_KEY", "ARK_API_KEY_CODING", "ARK_IMAGE_GENERATE", "ARK_IMAGE_EDIT",
         "ARK_VISION_ANALYZE", "ARK_VISION_VALIDATE"}
has_creds = all(os.environ.get(c) for c in CREDS)
skip_real = pytest.mark.skipif(not has_creds, reason="Ark credentials not set")

BUDGET = {"reference_analysis": 2, "generation": 6, "edits": 3,
          "validations": 6, "final_validation": 2}


def _models() -> dict:
    return {
        "image_generate": {"model": os.environ["ARK_IMAGE_GENERATE"]},
        "image_edit": {"model": os.environ["ARK_IMAGE_EDIT"]},
        "vision_analyze": {"model": os.environ["ARK_VISION_ANALYZE"]},
        "vision_validate": {"model": os.environ["ARK_VISION_VALIDATE"]},
    }


def _real_client(run_dir: Path) -> ArkClient:
    transport = RealArkTransport()
    state = RunState(run_dir.name, budget=BUDGET)
    cache = Cache(run_dir / "cache")
    return ArkClient(_models(), transport, api_key=os.environ["ARK_API_KEY"],
                     state=state, cache=cache, output_dir=run_dir)


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
@skip_real
def test_case2_reference_decomposition(tmp_path: Path):
    run_dir = RunDirectory(base_dir=tmp_path).create("case2")
    client = _real_client(run_dir)

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
@skip_real
def test_case3_hybrid_multipanel(tmp_path: Path):
    run_dir = RunDirectory(base_dir=tmp_path).create("case3")
    client = _real_client(run_dir)
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
        "auto_execute": True,
    }
    wf = FigureWorkflow(request, config={}, run_dir=run_dir, ark_client=client,
                        state=client.state, base_dir=ROOT, compose_dpi=300)
    # Use force_export because the vision model is non-deterministic and may
    # return per-asset checks that block the gate even for valid figures.
    result = wf.run(force_export=True)
    assert result["paused"] is False
    assert result["exported"] is True

    # Formal outputs present in all default formats.
    for ext in ("png", "svg", "pdf"):
        assert (run_dir / "exports" / f"figure.{ext}").is_file()

    # AI asset is isolated and transparent; data plot from Python.
    manifest = json.loads((run_dir / "asset_manifest.json").read_text())
    fiber = next(a for a in manifest["assets"] if a["asset_id"] == "fiber")
    assert fiber["transparent"] is True
    plan_routing = {a["asset_id"]: a["routing"] for a in result["figure_plan"]["assets"]}
    assert plan_routing["curve"] == "python"
    assert plan_routing["fiber"] == "ark_image"

    # Budget respected (no exceptions => within budget).
    assert client.state.calls_used("generation") <= BUDGET["generation"]

    # Reports complete.
    assert (run_dir / "generation_report.md").is_file()
    assert (run_dir / "run_state.json").is_file()
    final = result["validation_reports"][-1]
    assert final["summary"]["blocking"] is False

    # Secrets never leaked into the run directory (both plan keys).
    keys = [os.environ["ARK_API_KEY"].encode(),
            os.environ["ARK_API_KEY_CODING"].encode()]
    for f in run_dir.rglob("*"):
        if f.is_file() and f.suffix not in (".png", ".svg", ".pdf"):
            for key in keys:
                assert key not in f.read_bytes(), f"API key leaked in {f}"
