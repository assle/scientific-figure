"""Figure QA engine (plan section 10).

Orchestrates deterministic final checks, source-aware geometry rules, and the
multimodal final check. The interface takes an ``AssembledFigure`` so callers
do not thread the figure's parts through a wide parameter list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from figure_tools.validation.evidence import generate_evidence
from figure_tools.validation.extractors.assembly import map_bbox
from figure_tools.validation.extractors.raster_ocr import detect_text_elements
from figure_tools.validation.models import AssembledFigure, read_layout_manifest
from figure_tools.validation.graph_structure import validate_graph_structure
from figure_tools.validation.formal_text import formal_text_checks
from figure_tools.validation.publication import publication_profile_checks
from figure_tools.provenance import hash_json
from figure_tools.validation.vlm_verify import VLMVerifier
from figure_tools.validation.rules import (
    asset_bounds,
    colorbar_collision,
    panel_label_collision,
    panel_label_consistency,
    text_clipping,
    text_text_overlap,
    minimum_font_size,
)
from figure_tools.validation.rules.ai_asset import unexpected_ai_text
from figure_tools.validation.summary import make_check, summarize_checks


def _deterministic_final_checks(
    figure_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    composed_image_path: str | Path,
    physical_size_mm: tuple[float, float],
    min_dpi: int,
) -> list[dict]:
    checks: list[dict] = []
    plan_assets = figure_plan.get("assets", [])
    manifest_by_id = {a["asset_id"]: a for a in asset_manifest.get("assets", [])}

    missing = []
    for a in plan_assets:
        m = manifest_by_id.get(a["asset_id"])
        if m is None or not Path(m["path"]).exists():
            missing.append(a["asset_id"])
    checks.append(make_check("missing_assets", "final", "error",
                         "fail" if missing else "pass",
                         "missing: " + ",".join(missing) if missing else "all assets present"))

    bad_alpha = [
        a["asset_id"] for a in plan_assets
        if a["type"] == "image_asset"
        and not manifest_by_id.get(a["asset_id"], {}).get("transparent", False)
    ]
    checks.append(make_check("alpha_for_ai_assets", "final", "error",
                         "fail" if bad_alpha else "pass",
                         "non-transparent AI assets: " + ",".join(bad_alpha) if bad_alpha
                         else "AI assets transparent"))

    zorders = [a["z_order"] for a in plan_assets]
    dup = sorted({z for z in zorders if zorders.count(z) > 1})
    checks.append(make_check("z_order_unique", "final", "error",
                         "fail" if dup else "pass",
                         "duplicate z_order: " + ",".join(map(str, dup)) if dup
                         else "z_order unique"))

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

    return checks


def _multimodal_final_checks(
    provider_client: Any,
    composed_image_path: str | Path,
    physical_size_mm: tuple[float, float],
    structure_questions: list[str] | None = None,
) -> list[dict]:
    if provider_client is None:
        return [make_check("multimodal_final", "final", "warning", "skipped",
                       "no provider client; multimodal final check skipped")]
    try:
        raw = provider_client.validate_final_figure(
            composed_image_path,
            physical_size_mm=physical_size_mm,
            checks=structure_questions,
        )
    except Exception as e:  # noqa: BLE001
        return [make_check("multimodal_final", "final", "warning", "skipped",
                       f"multimodal final check unavailable: {e}")]
    if not raw:
        return [make_check("multimodal_final", "final", "error", "fail",
                       "multimodal final check returned no checks")]
    out: list[dict] = []
    for c in raw:
        c.setdefault("scope", "final")
        c.setdefault("level", "error")
        out.append(c)
    return out


def _figure_graph_checks(
    figure_plan: dict[str, Any],
    composed_image_path: str | Path,
    asset_manifest: dict[str, Any],
    manifest: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    graph_ref = figure_plan.get("figure_graph_ref") or {}
    layout_ref = figure_plan.get("solved_layout_ref") or {}
    if not graph_ref or not layout_ref:
        return [make_check(
            "figure_graph_checks",
            "final",
            "warning",
            "skipped",
            "Figure plan has no Figure Graph references",
        )], []
    run_dir = Path(composed_image_path).parent.parent

    def load(reference: dict[str, Any]) -> dict[str, Any]:
        relative = Path(str(reference.get("artifact") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Figure Graph references must stay inside the run")
        value = json.loads((run_dir / relative).read_text(encoding="utf-8"))
        if hash_json(value) != reference.get("content_hash"):
            raise ValueError(f"artifact hash mismatch: {relative}")
        return value

    try:
        graph = load(graph_ref)
        solved_layout = load(layout_ref)
    except Exception as exc:  # noqa: BLE001
        return [make_check(
            "figure_graph_checks",
            "final",
            "error",
            "fail",
            str(exc),
        )], []
    expected_node_ids = {str(item["node_id"]) for item in graph.get("nodes", [])}
    observed_nodes = [
        {"node_id": str(item["asset_id"])}
        for item in asset_manifest.get("assets", [])
        if str(item.get("asset_id")) in expected_node_ids
    ]
    observed_connectors = []
    observed_groups = []
    if manifest is not None:
        for element in manifest.elements:
            if element.element_type == "connector":
                observed_connectors.append({
                    "edge_id": element.element_id.removeprefix("edge:"),
                    "source_port": element.metadata.get("source_port", ""),
                    "target_port": element.metadata.get("target_port", ""),
                    "direction": element.metadata.get("direction", "forward"),
                })
            elif element.element_type == "group":
                observed_groups.append({
                    "group_id": element.element_id.removeprefix("group:"),
                    "node_ids": list(element.metadata.get("node_ids", [])),
                })
    graph_checks = validate_graph_structure(
        graph,
        {
            "nodes": observed_nodes,
            "connectors": observed_connectors,
            "groups": observed_groups,
        },
        conflicts=list(solved_layout.get("conflicts") or []),
    )
    question_ref = figure_plan.get("structure_questions_ref") or {}
    questions: list[dict[str, Any]] = []
    if question_ref:
        try:
            questions = list(load(question_ref).get("questions") or [])
        except Exception:  # noqa: BLE001
            questions = []
    status_by_level = {
        "component": graph_checks[0]["status"],
        "local_topology": graph_checks[1]["status"],
        "phase": graph_checks[2]["status"],
        "global_semantics": (
            "pass" if all(item["status"] == "pass" for item in graph_checks)
            else "fail"
        ),
    }
    for question in questions:
        level = str(question.get("level") or "global_semantics")
        graph_checks.append(make_check(
            f"structure_question_{level}",
            "final",
            "error" if question.get("critical") else "warning",
            status_by_level.get(level, "fail"),
            str(question.get("question") or "structure question"),
            method="rendered_structure_recovery",
        ))
    return graph_checks, [
        str(question.get("question")) for question in questions
        if question.get("question")
    ]


class FigureQAEngine:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        provider_client: Any = None,
        ocr_backend: Any = None,
    ) -> None:
        self.config = config or {}
        self.provider_client = provider_client
        if ocr_backend is not None:
            self.ocr_backend = ocr_backend
        else:
            from figure_tools.validation.extractors.raster_ocr import get_ocr_backend
            self.ocr_backend = get_ocr_backend(self.config)
        det = self.config.get("deterministic", {})
        if not isinstance(det, dict):
            det = {}
        self._det = det
        self.thresholds = self.config.get("thresholds", {}) or {}

    def _rule_enabled(self, name: str) -> bool:
        return bool(self._det.get(name, True))

    def _ocr_ai_text_checks(
        self,
        asset_manifest: dict[str, Any],
        manifest,
        asset_placements: dict[str, list[float]] | None,
    ) -> list[dict]:
        if self.ocr_backend is None:
            return [make_check("unexpected_ai_text", "final", "warning", "skipped",
                               "no OCR backend; AI-asset text check skipped")]
        detections: list[tuple[str, list]] = []
        for a in asset_manifest.get("assets", []):
            if a.get("type") != "image_asset":
                continue
            path = a.get("path")
            if not path or not Path(path).exists():
                continue
            detected = detect_text_elements(path, self.ocr_backend)
            # Map detected bboxes (asset pixels) onto the final canvas when the
            # placement is known, so evidence crops locate the right region.
            placement = (asset_placements or {}).get(a["asset_id"])
            dims = a.get("pixel_dimensions")
            if placement and dims and len(dims) == 2 and manifest is not None:
                sw, sh = int(dims[0]), int(dims[1])
                for el in detected:
                    el.bbox = map_bbox(el.bbox, placement,
                                       manifest.canvas_width_px,
                                       manifest.canvas_height_px, sw, sh)
                    el.panel_id = None
            detections.append((a["asset_id"], detected))
        return unexpected_ai_text(detections)

    def _layout_checks(self, manifest) -> list[dict]:
        checks: list[dict] = []
        th = self.thresholds
        if self._rule_enabled("text_overlap"):
            checks.extend(text_text_overlap(manifest, th))
        if self._rule_enabled("clipping"):
            checks.extend(text_clipping(manifest, th))
            checks.extend(asset_bounds(manifest, th))
        if self._rule_enabled("panel_labels"):
            checks.extend(panel_label_collision(manifest, th))
            checks.extend(panel_label_consistency(manifest, th))
        if self._rule_enabled("typography"):
            checks.extend(minimum_font_size(manifest, th))
        if self._rule_enabled("colorbar_collision"):
            checks.extend(colorbar_collision(manifest, th))
        return checks

    def validate_final(
        self,
        figure: AssembledFigure,
        run_id: str | None = None,
        min_dpi: int = 300,
        evidence_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        checks: list[dict] = []
        checks.extend(_deterministic_final_checks(
            figure.figure_plan, figure.asset_manifest, figure.image_path,
            figure.physical_size_mm, min_dpi))

        manifest = None
        if figure.layout_manifest_path and Path(figure.layout_manifest_path).exists():
            try:
                manifest = read_layout_manifest(figure.layout_manifest_path)
            except Exception:  # noqa: BLE001
                manifest = None

        graph_checks, structure_questions = _figure_graph_checks(
            figure.figure_plan,
            figure.image_path,
            figure.asset_manifest,
            manifest,
        )
        checks.extend(graph_checks)

        if manifest is not None:
            checks.extend(self._layout_checks(manifest))
        else:
            # Degraded validation: geometry rules cannot run without source
            # metadata. Report it explicitly so a missing manifest is never
            # mistaken for a pass.
            checks.append(make_check(
                "geometry_checks_skipped", "final", "warning", "skipped",
                "no layout manifest; geometry rules skipped"))

        checks.extend(formal_text_checks(figure.figure_plan, manifest))

        checks.extend(publication_profile_checks(
            str(figure.figure_plan.get("publication_profile") or "general"),
            manifest,
            figure.physical_size_mm,
            editable_svg_exists=Path(figure.image_path).with_suffix(".svg").is_file(),
        ))

        # OCR fallback for raster/AI assets without layout metadata (plan 15).
        checks.extend(self._ocr_ai_text_checks(
            figure.asset_manifest, manifest, figure.asset_placements))

        # Evidence crops for localized layout failures (plan section 13).
        ev_cfg = self.config.get("evidence", {})
        if not isinstance(ev_cfg, dict):
            ev_cfg = {}
        if evidence_dir is not None and ev_cfg.get("enabled", True):
            generate_evidence(figure.image_path, checks, evidence_dir, ev_cfg)

        # Local VLM review of suspicious regions (plan section 14).
        VLMVerifier(self.provider_client, self.config).review(checks)

        checks.extend(_multimodal_final_checks(
            self.provider_client,
            figure.image_path,
            figure.physical_size_mm,
            structure_questions,
        ))

        return {
            "schema_version": "1.0",
            "run_id": run_id or figure.figure_plan.get("run_id", "final"),
            "checks": checks,
            "summary": summarize_checks(checks),
        }


__all__ = ["FigureQAEngine"]
