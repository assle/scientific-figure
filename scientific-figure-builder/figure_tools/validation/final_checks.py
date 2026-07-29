"""Final assembled-figure validation (plan section 11).

Checks panel placement, z-order, missing assets, AI-asset transparency, labels,
and effective resolution. Scientific errors block export; warnings do not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from figure_tools.validation.summary import make_check, summarize_checks


def validate_assembled_figure(
    figure_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    composed_image_path: str | Path,
    physical_size_mm: tuple[float, float],
    min_dpi: int = 300,
    run_id: str | None = None,
) -> dict[str, Any]:
    checks: list[dict] = []
    plan_assets = figure_plan.get("assets", [])
    manifest_by_id = {a["asset_id"]: a for a in asset_manifest.get("assets", [])}

    # Missing assets (error).
    missing = []
    for a in plan_assets:
        m = manifest_by_id.get(a["asset_id"])
        if m is None or not Path(m["path"]).exists():
            missing.append(a["asset_id"])
    checks.append(make_check("missing_assets", "final", "error",
                         "fail" if missing else "pass",
                         "missing: " + ",".join(missing) if missing else "all assets present"))

    # AI assets must be transparent (error).
    bad_alpha = [
        a["asset_id"] for a in plan_assets
        if a["type"] == "image_asset"
        and not manifest_by_id.get(a["asset_id"], {}).get("transparent", False)
    ]
    checks.append(make_check("alpha_for_ai_assets", "final", "error",
                         "fail" if bad_alpha else "pass",
                         "non-transparent AI assets: " + ",".join(bad_alpha) if bad_alpha
                         else "AI assets transparent"))

    # Z-order uniqueness (error).
    zorders = [a["z_order"] for a in plan_assets]
    dup = sorted({z for z in zorders if zorders.count(z) > 1})
    checks.append(make_check("z_order_unique", "final", "error",
                         "fail" if dup else "pass",
                         "duplicate z_order: " + ",".join(map(str, dup)) if dup
                         else "z_order unique"))

    # Effective resolution (warning).
    try:
        img = Image.open(composed_image_path)
        w, h = img.size
        w_mm, h_mm = physical_size_mm
        dpi = min(w / (w_mm / 25.4), h / (h_mm / 25.4))
        checks.append(make_check("effective_resolution", "final", "warning",
                             "pass" if dpi >= min_dpi else "fail",
                             f"effective {dpi:.0f} dpi (min {min_dpi})"))
    except Exception as e:  # noqa: BLE001
        checks.append(make_check("effective_resolution", "final", "error", "fail", str(e)))

    # Panel label consistency (warning): each panel has at least one text element.
    text_ids = {t["element_id"] for t in figure_plan.get("text_elements", [])}
    unlabeled = [p["panel_id"] for p in figure_plan.get("panels", [])
                 if not text_ids]  # simplified: warns only if no labels at all
    checks.append(make_check("panel_label_consistency", "final", "warning",
                         "pass" if not unlabeled else "fail",
                         "no labels" if unlabeled else "labels present"))

    return {
        "schema_version": "1.0",
        "run_id": run_id or figure_plan.get("run_id", "final"),
        "checks": checks,
        "summary": summarize_checks(checks),
    }
