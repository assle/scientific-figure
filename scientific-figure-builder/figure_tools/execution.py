"""Figure Execution Module for approved plans and publication outputs."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from figure_tools.assembly.compositor import compose_assets
from figure_tools.export.publish import export_figure
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.planning.geometry import resolve_asset_bbox
from figure_tools.provenance import hash_file
from figure_tools.publication_profiles import get_publication_profile
from figure_tools.report import write_generation_report
from figure_tools.run_store import RunStore
from figure_tools.validation.engine import FigureQAEngine
from figure_tools.validation.models import AssembledFigure
from figure_tools.validation.root_cause import analyze_root_causes
from figure_tools.vector.primitives import SvgCanvas
from figure_tools.vector.svg_normalize import normalize_svg_bytes, resolve_export_target


class FigureExecution:
    def __init__(
        self,
        request: dict[str, Any],
        config: dict[str, Any],
        run_dir: str | Path,
        provider_client: Any,
        state: Any,
        base_dir: str | Path = ".",
        compose_dpi: int = 300,
    ) -> None:
        self.request = request
        self.config = config
        self.run_dir = Path(run_dir)
        self.provider = provider_client
        self.state = state
        self.base_dir = Path(base_dir)
        self.compose_dpi = compose_dpi
        self.store = RunStore(self.run_dir)

    def _canvas_mm(self) -> tuple[float, float]:
        c = self.request["canvas"]
        return float(c["width"]), float(c["height"])

    def execute_plan(
        self,
        plan: dict[str, Any],
        export_target: str | None = None,
        style_anchor_approved: bool = False,
        layout_report: dict[str, Any] | None = None,
        pre_rendered_assets: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Render and validate an approved plan, without publishing exports."""
        planned_request = self._request_from_plan(plan)
        if planned_request is not None:
            self.request = planned_request
        export_target = export_target or self._export_target()
        ai_elements = [
            (panel, el)
            for panel in self.request["panels"]
            for el in panel.get("elements", [])
            if el["type"] == "image_asset"
        ]
        conditions = self._generation_conditions()
        grouped_assets: dict[str, list[tuple[dict, dict]]] = {}
        for panel, element in ai_elements:
            grouped_assets.setdefault(
                str(element.get("style_group") or "figure"), []
            ).append((panel, element))
        style_anchors: dict[str, dict[str, Any]] = {}
        reusable = dict(pre_rendered_assets or {})
        for style_group, members in grouped_assets.items():
            if len(members) < 2:
                continue
            anchor_id = members[0][1]["element_id"]
            anchor_path = self.run_dir / "assets" / f"{anchor_id}.png"
            anchor_meta = reusable.get(anchor_id)
            if (
                anchor_meta is None
                or not anchor_path.is_file()
                or anchor_meta.get("content_hash") != hash_file(anchor_path)
            ):
                anchor_meta = self._generate_condition(
                    conditions[anchor_id], anchor_path,
                )
                reusable[anchor_id] = anchor_meta
            style_anchors[style_group] = {
                "asset_id": anchor_id,
                "path": str(anchor_path),
                "content_hash": anchor_meta["content_hash"],
            }
        if style_anchors and not style_anchor_approved:
            self.store.commit_json("plans/pre_rendered_assets.json", reusable)
            return {"paused": True, "pause_reason": "style_anchor_approval"}
        if style_anchors:
            from figure_tools.planning.artifacts import FigurePlanningArtifacts

            condition_artifact = FigurePlanningArtifacts(
                self.request,
                self.config,
                self.run_dir,
                self.provider,
                base_dir=self.base_dir,
            ).refresh_generation_conditions(plan, style_anchors=style_anchors)
            conditions = {
                item["asset_id"]: item
                for item in condition_artifact["conditions"]
            }
            pre_rendered_assets = reusable

        manifest_assets, validation_reports, placements, text_placements = \
            self._render_assets(plan, ai_elements, export_target, conditions,
                                pre_rendered_assets=pre_rendered_assets)
        manifest = {"schema_version": "1.0", "assets": manifest_assets}
        self.store.commit_json("asset_manifest.json", manifest)

        assembly_dir = self.run_dir / "assembly"
        solved_layout = self.store.load_optional_json("plans/solved_layout.json") or {}
        source_layouts = {
            p["asset_id"]: p["layout_manifest"]
            for p in placements
            if p.get("asset_id") and p.get("layout_manifest")
            and Path(p["layout_manifest"]).exists()
        }
        assembly_result = compose_assets(
            placements, output_dir=assembly_dir,
            canvas_mm=self._canvas_mm(), dpi=self.compose_dpi,
            text_placements=text_placements, source_layouts=source_layouts,
            connectors=list(solved_layout.get("connectors") or []),
            groups=list(solved_layout.get("groups") or []),
            export_target=export_target,
        )
        composed_png = Path(assembly_result["files"]["png"])
        final = FigureQAEngine(
            config=self.config.get("validation", {}),
            provider_client=self.provider,
        ).validate_final(
            AssembledFigure(
                figure_plan=plan, asset_manifest=manifest,
                image_path=composed_png,
                layout_manifest_path=assembly_result.get("layout_manifest"),
                physical_size_mm=self._canvas_mm(),
                asset_placements={p["asset_id"]: p["bbox"] for p in placements
                                  if p.get("asset_id")},
            ),
            run_id=self.state.run_id,
            evidence_dir=self.run_dir / "validation" / "evidence",
        )
        validation_reports.append(final)
        self.store.commit_json("validation/validation_report.json", final)
        self.store.commit_json("validation/final.json", final)

        if layout_report is None:
            layout_report = self.store.load_optional_json("plans/layout_analysis.json") or {}
        has_blocking_failures = any(
            any(c.get("status") == "fail" and c.get("level") == "error"
                for c in r.get("checks", []))
            for r in validation_reports
        )
        if has_blocking_failures:
            root_cause = analyze_root_causes(validation_reports, plan, layout_report)
            self.store.commit_json("validation/root_cause_report.json", root_cause)
        self.store.commit_json(
            "run_state.json", self.state.to_dict(), schema="run-state.schema.json"
        )
        return {
            "paused": False,
            "manifest": manifest,
            "validation_reports": validation_reports,
            "assembly_result": assembly_result,
            "placements": placements,
            "text_placements": text_placements,
        }

    def _request_from_plan(self, plan: dict[str, Any]) -> dict[str, Any] | None:
        """Reconstruct execution input from an approved plan artifact.

        Plans created before source snapshots were introduced fall back to the
        caller-provided request for compatibility.
        """
        source_assets = [asset for asset in plan.get("assets", []) if asset.get("source")]
        if not source_assets and plan.get("assets"):
            return None
        panels = [
            {
                "panel_id": panel["panel_id"],
                "bbox": list(panel["bbox"]),
                "physical_size": list(panel["physical_size"]),
                "elements": [],
            }
            for panel in plan.get("panels", [])
        ]
        panels_by_id = {panel["panel_id"]: panel for panel in panels}
        labels: list[dict[str, Any]] = []
        for asset in source_assets:
            source = copy.deepcopy(asset["source"])
            if asset.get("type") in {"text", "equation"}:
                labels.append(source)
                continue
            panel_id = asset.get("panel_id")
            if panel_id in panels_by_id:
                panels_by_id[panel_id]["elements"].append(source)
        if not labels:
            labels = [copy.deepcopy(item) for item in plan.get("text_elements", [])]
        delivery = dict(plan.get("delivery") or {})
        return {
            "figure_id": plan["figure_id"],
            "run_id": plan.get("run_id", plan["figure_id"]),
            "canvas": copy.deepcopy(plan["canvas"]),
            "units": plan.get("units", "mm"),
            "panels": panels,
            "labels": labels,
            "assumptions": list(plan.get("assumptions", [])),
            "uncertainties": list(plan.get("uncertainties", [])),
            "user_input_requirements": [],
            "reference_figures": [
                item["path"] for item in plan.get("planned_uploads", [])
            ],
            "export_target": delivery.get("export_target", "general"),
            "figure_width_cm": delivery.get("figure_width_cm"),
            "include_pptx": delivery.get("include_pptx", False),
            "language": plan.get("language", "zh"),
            "style": plan.get("style", plan.get("style_bible_ref", "default")),
            "publication_profile": plan.get("publication_profile", "general"),
            "brief_ref": plan.get("brief_ref"),
            "auto_execute": True,
        }

    def publish(
        self,
        prepared: dict[str, Any],
        execution: dict[str, Any],
        force_export: bool = False,
        force_export_reason: str | None = None,
    ) -> dict[str, Any]:
        """Apply the Export gate and write the generation report."""
        assembly_dir = self.run_dir / "assembly"
        validation_reports = execution["validation_reports"]
        export_result = export_figure(
            validation_reports,
            source_dir=assembly_dir,
            output_dir=self.run_dir / "exports",
            force_export=force_export,
        )
        exported = bool(export_result["files"])
        export_blocked_reason = export_result["export_blocked_reason"]
        self.store.commit_json(
            "run_state.json", self.state.to_dict(), schema="run-state.schema.json"
        )
        report_path = write_generation_report(
            self.run_dir, prepared["plan"], execution["manifest"],
            validation_reports, run_state=self.state.to_dict(),
            exported=exported, force_export=force_export,
            force_export_reason=force_export_reason,
            export_blocked_reason=export_blocked_reason,
            export_target=prepared["export_target"],
        )
        return {
            "exported": exported,
            "files": dict(export_result["files"]),
            "export_blocked_reason": export_blocked_reason,
            "report_path": report_path,
        }

    def _zorder(self, asset_id: str, plan: dict) -> int:
        for a in plan["assets"]:
            if a["asset_id"] == asset_id:
                return a["z_order"]
        return 0

    def _export_target(self) -> str:
        value = self.request.get("export_target")
        if not value:
            value = (self.config.get("export") or {}).get("export_target")
        return resolve_export_target(value)

    def _generation_conditions(self) -> dict[str, dict[str, Any]]:
        artifact = self.store.load_optional_json("plans/generation_conditions.json")
        if artifact is None:
            raise ValueError(
                "approved Figure plan is missing its Generation Conditions"
            )
        return {
            str(item["asset_id"]): dict(item)
            for item in artifact.get("conditions", [])
        }

    def _generate_condition(
        self,
        condition: dict[str, Any],
        output_path: str | Path,
    ) -> dict[str, Any]:
        references = list(condition.get("references") or [])
        meta = self.provider.generate_image_asset(
            condition["prompt"],
            dict(condition.get("parameters") or {}),
            output_path=output_path,
            reference_hashes=[item["content_hash"] for item in references],
            reference_paths=[item["path"] for item in references],
            reference_descriptors=[
                {"role": item["role"], "strength": item["strength"]}
                for item in references
            ],
        )
        meta["condition_hash"] = condition["condition_hash"]
        return meta

    def _error_report(self, asset_id: str, detail: str) -> dict:
        from figure_tools.validation.summary import summarize_checks

        checks = [{"check_id": "render", "scope": f"asset:{asset_id}",
                   "level": "error", "status": "fail", "detail": detail}]
        return {"schema_version": "1.0", "run_id": asset_id,
                "checks": checks, "summary": summarize_checks(checks)}

    def _render_assets(self, plan, ai_elements, export_target: str, conditions,
                       pre_rendered_assets: dict[str, dict[str, Any]] | None = None):
        manifest_assets: list[dict] = []
        validation_reports: list[dict] = []
        placements: list[dict] = []

        # Data plots: local, sequential, deterministic.
        for panel in self.request["panels"]:
            for el in panel.get("elements", []):
                if el["type"] != "data_plot":
                    continue
                asset_id = el["element_id"]
                try:
                    spec = load_plot_spec(el["plot_spec"])
                    out = self.run_dir / "plots" / asset_id
                    path = out / "plot.png"
                    if not path.is_file():
                        render_plot(
                            spec,
                            output_dir=out,
                            base_dir=self.base_dir,
                            export_target=export_target,
                        )
                    manifest_assets.append(
                        self._local_meta(asset_id, "data_plot", path, plan, transparent=False))
                    placements.append({"asset_id": asset_id, "path": str(path),
                                       "bbox": self._placement_bbox(asset_id, plan, panel),
                                       "panel_id": panel["panel_id"],
                                       "z_order": self._zorder(asset_id, plan),
                                       "layout_manifest": str(out / "layout_manifest.json")})
                except Exception as e:  # noqa: BLE001
                    validation_reports.append(self._error_report(asset_id, str(e)))

        # AI assets: independent, concurrency 2 (plan section 12).
        ai_results: dict[str, tuple] = {}
        if ai_elements:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = {ex.submit(
                    self._safe_gen_ai, panel, el, conditions[el["element_id"]],
                    (pre_rendered_assets or {}).get(el["element_id"]),
                ): el["element_id"]
                        for panel, el in ai_elements}
                for fut in futs:
                    ai_results[futs[fut]] = fut.result()

        for panel, el in ai_elements:  # preserve plan order
            asset_id = el["element_id"]
            _aid, meta, report, err = ai_results[asset_id]
            if err is not None:
                validation_reports.append(self._error_report(asset_id, str(err)))
                continue
            if report is not None:
                validation_reports.append(report)
            manifest_assets.append(self._ai_manifest_entry(asset_id, meta, plan, report))
            placements.append({"asset_id": asset_id, "path": meta["path"],
                               "bbox": self._placement_bbox(asset_id, plan, panel),
                               "panel_id": panel["panel_id"],
                               "z_order": self._zorder(asset_id, plan)})

        text_placements = self._render_labels(plan, manifest_assets, export_target)
        return manifest_assets, validation_reports, placements, text_placements

    def _safe_gen_ai(self, panel, el, condition, pre_rendered_meta=None):
        try:
            path = self.run_dir / "assets" / f"{el['element_id']}.png"
            reusable_path = (
                Path(pre_rendered_meta["path"])
                if pre_rendered_meta is not None and pre_rendered_meta.get("path")
                else None
            )
            if (
                pre_rendered_meta is not None
                and reusable_path is not None
                and reusable_path.is_file()
                and pre_rendered_meta.get("content_hash") == hash_file(reusable_path)
                and pre_rendered_meta.get("condition_hash") == condition["condition_hash"]
            ):
                report = self.provider.validate_image_asset(
                    path, physical_size_mm=tuple(panel["physical_size"])
                )
                return (el["element_id"], pre_rendered_meta, report, None)
            candidate_count = int(el.get("candidate_count", 1))
            if not 1 <= candidate_count <= 4:
                raise ValueError("candidate_count must be between 1 and 4")
            if candidate_count > 1:
                meta, report = self._select_candidate(
                    el["element_id"], condition, panel, path, candidate_count,
                )
                return (el["element_id"], meta, report, None)
            meta = self._generate_condition(condition, path)
            report = self.provider.validate_image_asset(
                path, physical_size_mm=tuple(panel["physical_size"]))
            return (el["element_id"], meta, report, None)
        except Exception as e:  # noqa: BLE001
            return (el["element_id"], None, None, e)

    def _select_candidate(
        self,
        asset_id: str,
        condition: dict[str, Any],
        panel: dict[str, Any],
        output_path: Path,
        candidate_count: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candidates: list[tuple[tuple[int | float, ...], dict, dict, Path]] = []
        records = []
        for index in range(1, candidate_count + 1):
            candidate_path = (
                self.run_dir / "assets" / "candidates" / f"{asset_id}-{index}.png"
            )
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_condition = copy.deepcopy(condition)
            candidate_condition["parameters"] = {
                **dict(candidate_condition.get("parameters") or {}),
                "candidate_index": index,
            }
            meta = self._generate_condition(candidate_condition, candidate_path)
            report = self.provider.validate_image_asset(
                candidate_path,
                physical_size_mm=tuple(panel["physical_size"]),
                checks=[
                    f"component fidelity for {asset_id}",
                    "structural fidelity to the Generation Condition",
                    "no unexpected text or symbols",
                    "Publication profile asset quality",
                    "Style group consistency",
                    "aesthetic quality",
                ],
            )
            summary = report.get("summary") or {}
            report_checks = list(report.get("checks") or [])
            semantic_checks = [
                item for item in report_checks
                if any(token in str(item.get("check_id", "")) for token in (
                    "semantic", "component", "object", "count", "structure",
                ))
            ]
            style_checks = [
                item for item in report_checks
                if any(token in str(item.get("check_id", "")) for token in (
                    "style", "aesthetic", "visual_quality",
                ))
            ]
            semantic_failures = sum(
                item.get("status") == "fail" for item in semantic_checks
            )
            semantic_passes = sum(
                item.get("status") == "pass" for item in semantic_checks
            )
            style_failures = sum(
                item.get("status") == "fail" for item in style_checks
            )
            style_score = max(
                (float(item.get("confidence", 0.0)) for item in style_checks),
                default=0.0,
            )
            rank = (
                1 if summary.get("blocking") else 0,
                int(summary.get("errors", 0)),
                semantic_failures,
                -semantic_passes,
                style_failures,
                -style_score,
                int(summary.get("warnings", 0)),
                -int(summary.get("passed", 0)),
            )
            candidates.append((rank, meta, report, candidate_path))
            records.append({
                "candidate": index,
                "path": str(candidate_path),
                "content_hash": meta["content_hash"],
                "blocking": bool(summary.get("blocking")),
                "errors": int(summary.get("errors", 0)),
                "warnings": int(summary.get("warnings", 0)),
                "passed": int(summary.get("passed", 0)),
                "semantic_failures": semantic_failures,
                "semantic_passes": semantic_passes,
                "style_failures": style_failures,
                "style_score": style_score,
            })
        selected_index, selected = min(
            enumerate(candidates, start=1), key=lambda item: item[1][0]
        )
        _rank, meta, report, selected_path = selected
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(selected_path, output_path)
        selected_meta = copy.deepcopy(meta)
        selected_meta["path"] = str(output_path)
        selected_meta["content_hash"] = hash_file(output_path)
        self.store.commit_json(
            f"validation/candidate_selection/{asset_id}.json",
            {
                "schema_version": "1.0",
                "asset_id": asset_id,
                "selected_candidate": selected_index,
                "selection_policy": "authoritative-gates-then-quality",
                "candidates": records,
            },
        )
        return selected_meta, report

    def _placement_bbox(self, asset_id: str, plan: dict, panel: dict) -> list[float]:
        asset = next(
            (
                item for item in plan.get("assets", [])
                if item.get("asset_id") == asset_id
            ),
            None,
        )
        if not asset or not asset.get("bbox"):
            return list(panel["bbox"])
        return resolve_asset_bbox(asset, panel)

    def _render_labels(self, plan, manifest_assets, export_target: str) -> list[dict]:
        text_placements: list[dict] = []
        profile = get_publication_profile(
            str(self.request.get("publication_profile") or "general")
        )
        for i, label in enumerate(self.request.get("labels", [])):
            asset_id = label["element_id"]
            font_size = (
                float(profile.get("panel_label_pt", 9))
                if label.get("kind", "label") == "label"
                else float((profile.get("ordinary_text_pt") or [7, 9])[-1])
            )
            svg_path = self.run_dir / "vectors" / f"{asset_id}.svg"
            if not svg_path.is_file():
                canvas = SvgCanvas(width=200, height=40)
                canvas.text(
                    2, 16, label["content"], font_size=font_size, fill="#000000"
                )
                svg = normalize_svg_bytes(
                    canvas.to_string().encode("utf-8"), export_target=export_target
                ).decode("utf-8")
                self.store.commit_text(f"vectors/{asset_id}.svg", svg)
            manifest_assets.append(self._vector_meta(asset_id, "text", svg_path, plan))
            panel = self.request["panels"][i] if i < len(self.request["panels"]) else None
            if panel is not None:
                text_placements.append({
                    "x": panel["bbox"][0] + 0.02,
                    "y": panel["bbox"][1] + 0.02,
                    "text": label["content"],
                    "font_size": font_size,
                    "element_id": asset_id,
                    "kind": label.get("kind", "label"),
                    "panel_id": panel["panel_id"],
                })
        return text_placements

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def _local_meta(self, asset_id, atype, path, plan, transparent):
        from PIL import Image

        img = Image.open(path)
        return {
            "asset_id": asset_id, "type": atype, "path": str(path),
            "content_hash": hash_file(path),
            "pixel_dimensions": list(img.size), "transparent": transparent,
            "z_order": self._zorder(asset_id, plan),
            "validation_result": {"status": "pass"},
            "provenance": {"endpoint_id": "python", "seed": None, "timestamp": self._now()},
            "parent_asset_id": None,
        }

    def _ai_manifest_entry(self, asset_id, meta, plan, report):
        status = "pass"
        if report is not None and report["summary"]["blocking"]:
            status = "fail"
        return {
            "asset_id": asset_id, "type": "image_asset",
            "path": meta["path"], "content_hash": meta["content_hash"],
            "generation": {"model": meta["model"], "parameters": meta["parameters"]},
            "prompt_hash": meta["prompt_hash"],
            "condition_hash": meta.get("condition_hash"),
            "reference_hashes": meta["reference_hashes"],
            "pixel_dimensions": meta["pixel_dimensions"],
            "transparent": meta["transparent"],
            "z_order": self._zorder(asset_id, plan),
            "validation_result": {"status": status},
            "provenance": meta["provenance"],
            "parent_asset_id": meta.get("parent_asset_id"),
        }

    def _vector_meta(self, asset_id, atype, path, plan):
        return {
            "asset_id": asset_id, "type": atype, "path": str(path),
            "content_hash": hash_file(path),
            "pixel_dimensions": [int(self._canvas_mm()[0] / 25.4 * self.compose_dpi),
                                 int(self._canvas_mm()[1] / 25.4 * self.compose_dpi)],
            "transparent": True, "z_order": self._zorder(asset_id, plan),
            "validation_result": {"status": "pass"},
            "provenance": {"endpoint_id": "svg", "seed": None, "timestamp": self._now()},
            "parent_asset_id": None,
        }
