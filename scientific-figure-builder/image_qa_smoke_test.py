"""End-to-end Image QA smoke test on a deliberately overlapping figure.

Builds a matplotlib figure with real layout problems:
  - panel label "(a)" placed over the y-axis label   -> panel_label_collision
  - two text annotations that overlap each other      -> text_text_overlap
Renders PNG + layout_manifest.json, runs FigureQAEngine, prints findings
and writes evidence crops.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from figure_tools.validation.extractors.matplotlib import extract_matplotlib_layout  # noqa: E402
from figure_tools.validation.engine import FigureQAEngine  # noqa: E402
from figure_tools.validation.models import (  # noqa: E402
    AssembledFigure,
    write_layout_manifest,
)

OUT = Path("/var/folders/j5/sylxhk5s06dgnyxs17gy9ssc0000gn/T/opencode/image_qa_test")
OUT.mkdir(parents=True, exist_ok=True)


def build_overlapping_figure():
    fig, ax = plt.subplots(figsize=(5, 3.5))
    x = np.linspace(-2, 2, 50)
    ax.plot(x, np.exp(-x**2) * 100, "-o", label="measured")
    ax.set_title("Coupling efficiency")
    ax.set_xlabel("Lateral offset (um)")
    ax.set_ylabel("Efficiency (%)")

    # Problem 1: panel label "(a)" deliberately placed ON the y-axis label.
    # axes coords: (0,0.5) is the left-middle where the ylabel lives.
    ax.text(0.0, 0.5, "(a)", transform=ax.transAxes, fontsize=14,
            fontweight="bold", va="center", ha="left", zorder=20)

    # Problem 2: two text annotations that overlap each other (top-right).
    ax.text(0.70, 0.90, "peak region", transform=ax.transAxes, fontsize=10,
            color="red", zorder=15)
    ax.text(0.72, 0.88, "fit residual", transform=ax.transAxes, fontsize=10,
            color="blue", zorder=15)

    fig.canvas.draw()
    return fig


def main():
    fig = build_overlapping_figure()
    png_path = OUT / "overlap_figure.png"
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Re-render at the same geometry the extractor will see (no bbox_inches change).
    fig = build_overlapping_figure()
    fig.canvas.draw()
    fig.savefig(png_path, dpi=200)  # consistent geometry for bbox extraction
    manifest = extract_matplotlib_layout(fig, "plot:overlap_test")
    man_path = write_layout_manifest(OUT / "layout_manifest.json", manifest)
    plt.close(fig)

    print(f"Image:      {png_path}")
    print(f"Manifest:   {man_path}")
    print(f"Canvas:     {manifest.canvas_width_px} x {manifest.canvas_height_px} px")
    print(f"Elements:   {len(manifest.elements)}")
    print("Element types:", sorted({e.element_type for e in manifest.elements}))
    print()

    # Run the QA engine with evidence generation.
    engine = FigureQAEngine(
        config={
            "thresholds": {
                "minimum_overlap_pixels": 2,
                "overlap_warning_ratio": 0.01,
                "overlap_error_ratio": 0.03,
            },
            "evidence": {"enabled": True, "crop_padding_pixels": 30,
                         "crop_scale": 4, "draw_boxes": True},
        },
        provider_client=None,  # offline: multimodal/VLM skipped
    )
    plan = {"schema_version": "1.0", "figure_id": "overlap_test", "run_id": "overlap",
            "assets": [], "text_elements": [], "approval": {"status": "approved"}}
    asset_manifest = {"schema_version": "1.0", "assets": []}
    report = engine.validate_final(
        AssembledFigure(
            figure_plan=plan,
            asset_manifest=asset_manifest,
            image_path=png_path,
            layout_manifest_path=man_path,
            physical_size_mm=(127.0, 88.9),
        ),
        run_id="overlap_test",
        evidence_dir=OUT / "evidence",
    )

    print("=== Validation summary ===")
    print(json.dumps(report["summary"], indent=2))
    print()
    print("=== Failing checks ===")
    for c in report["checks"]:
        if c["status"] == "fail":
            print(f"- [{c['level']}] {c['check_id']}: {c.get('detail','')}")
            if c.get("element_ids"):
                print(f"    elements: {c['element_ids']}")
            if c.get("bbox"):
                print(f"    bbox: {[round(v,1) for v in c['bbox']]}")
            if c.get("method"):
                print(f"    method: {c['method']}")
            if c.get("evidence_path"):
                print(f"    evidence: {c['evidence_path']}")
            if c.get("repair_action"):
                print(f"    repair: {c['repair_action']}")
            print()

    ev_dir = OUT / "evidence"
    if ev_dir.exists():
        print("=== Evidence crops ===")
        for p in sorted(ev_dir.iterdir()):
            print(f"  {p.name}  ({p.stat().st_size} bytes)")

    (OUT / "validation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report: {OUT / 'validation_report.json'}")


if __name__ == "__main__":
    main()
