"""Final assembled-figure validation (plan section 11).

Public entry point kept stable; delegates to ``FigureQAEngine`` (plan section
10). Deterministic checks always run; geometry rules run when a layout manifest
is available; the multimodal final check runs when an ark client is provided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from figure_tools.validation.engine import FigureQAEngine


def validate_assembled_figure(
    figure_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    composed_image_path: str | Path,
    physical_size_mm: tuple[float, float],
    min_dpi: int = 300,
    run_id: str | None = None,
    layout_manifest_path: str | Path | None = None,
    ark_client: Any = None,
    qa_config: dict[str, Any] | None = None,
    evidence_dir: str | Path | None = None,
    asset_placements: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    engine = FigureQAEngine(config=qa_config, ark_client=ark_client)
    return engine.validate_final(
        figure_plan=figure_plan,
        asset_manifest=asset_manifest,
        image_path=composed_image_path,
        layout_manifest_path=layout_manifest_path,
        physical_size_mm=physical_size_mm,
        run_id=run_id or figure_plan.get("run_id", "final"),
        min_dpi=min_dpi,
        evidence_dir=evidence_dir,
        asset_placements=asset_placements,
    )
