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
from figure_tools.planning.layout_analysis import analyze_layout
from figure_tools.provenance import hash_file
from figure_tools.report import write_generation_report
from figure_tools.run_store import RunStore
from figure_tools.validation.engine import FigureQAEngine
from figure_tools.validation.models import AssembledFigure
from figure_tools.validation.root_cause import analyze_root_causes
from figure_tools.vector.primitives import SvgCanvas
from figure_tools.vector.svg_normalize import normalize_svg_bytes, resolve_export_target
from figure_tools.vector.wireframe import generate_wireframe


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

    def prepare_plan_artifacts(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Persist the deterministic artifacts derived from one Figure plan."""
        self.store.commit_json("plans/figure_plan.json", plan)
        self.store.commit_text("plans/layout_wireframe.svg", generate_wireframe(plan))

        data_chars = self._collect_data_characteristics()
        layout_report = analyze_layout(plan, data_chars)
        self.store.commit_json("plans/layout_analysis.json", layout_report)
        self._write_style_bible()
        self._copy_inputs()
        return layout_report

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
        if len(ai_elements) >= 3:
            anchor_id = ai_elements[0][1]["element_id"]
            anchor_path = self.run_dir / "assets" / f"{anchor_id}.png"
            anchor_meta = None
            if not anchor_path.exists():
                anchor_meta = self.provider.generate_image_asset(
                    ai_elements[0][1]["prompt"], {}, output_path=anchor_path)
            if not style_anchor_approved:
                if anchor_meta is not None:
                    self.store.commit_json(
                        "plans/pre_rendered_assets.json", {anchor_id: anchor_meta}
                    )
                return {"paused": True, "pause_reason": "style_anchor_approval"}

        manifest_assets, validation_reports, placements, text_placements = \
            self._render_assets(plan, ai_elements, export_target,
                                pre_rendered_assets=pre_rendered_assets)
        manifest = {"schema_version": "1.0", "assets": manifest_assets}
        self.store.commit_json("asset_manifest.json", manifest)

        assembly_dir = self.run_dir / "assembly"
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

    def _write_style_bible(self) -> None:
        from figure_tools._resources import template_path

        style = self.request.get("style", "default")
        destination = self.run_dir / "style_bible.json"
        if isinstance(style, dict):
            self.store.commit_json("style_bible.json", style)
            return
        if isinstance(style, str) and style not in {"", "default"}:
            candidate = Path(style)
            if candidate.is_file():
                shutil.copyfile(candidate, destination)
                return
        src = template_path("default-style-bible.json")
        self.store.commit_json(
            "style_bible.json", json.loads(src.read_text(encoding="utf-8"))
        )

    def _copy_inputs(self) -> None:
        inputs = self.run_dir / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        for ref in self.request.get("reference_figures", []):
            src = Path(ref)
            if src.exists():
                shutil.copyfile(src, inputs / src.name)
        for panel in self.request["panels"]:
            for el in panel.get("elements", []):
                if el["type"] == "data_plot":
                    try:
                        spec = load_plot_spec(el["plot_spec"])
                        src = self.base_dir / spec.source_data["path"]
                        if src.exists():
                            shutil.copyfile(src, inputs / src.name)
                    except Exception:  # noqa: BLE001
                        pass

    def _error_report(self, asset_id: str, detail: str) -> dict:
        from figure_tools.validation.summary import summarize_checks

        checks = [{"check_id": "render", "scope": f"asset:{asset_id}",
                   "level": "error", "status": "fail", "detail": detail}]
        return {"schema_version": "1.0", "run_id": asset_id,
                "checks": checks, "summary": summarize_checks(checks)}

    def _collect_data_characteristics(self) -> dict[str, Any]:
        panels: dict[str, Any] = {}
        labels = self.request.get("labels", [])
        for i, panel in enumerate(self.request["panels"]):
            pid = panel["panel_id"]
            element_count = 0
            label_len = 0
            densities = {
                "upper_left": 0.3, "upper_right": 0.3,
                "lower_left": 0.3, "lower_right": 0.3,
            }
            for el in panel.get("elements", []):
                element_count += 1
                if el["type"] == "data_plot":
                    try:
                        spec = load_plot_spec(el["plot_spec"])
                        element_count += max(len(spec.series) - 1, 0)
                        for v in spec.labels.values():
                            label_len = max(label_len, len(str(v)))
                        computed = self._compute_density(spec)
                        if computed:
                            densities = computed
                    except Exception:  # noqa: BLE001
                        pass
            if i < len(labels):
                label_len = max(label_len, len(labels[i].get("content", "")))
            panels[pid] = {
                "data_element_count": element_count,
                "label_text_length": label_len,
                "data_density_by_region": densities,
            }
        return {"panels": panels}

    def _compute_density(self, spec) -> dict[str, float] | None:
        import pandas as pd

        data_path = self.base_dir / spec.source_data["path"]
        if not data_path.exists():
            return None
        df = pd.read_csv(data_path)
        x_col = spec.column_mapping.get("x", "")
        y_col = spec.column_mapping.get("y", "")
        if x_col not in df.columns or y_col not in df.columns:
            return None
        x_mid = (df[x_col].min() + df[x_col].max()) / 2
        y_mid = (df[y_col].min() + df[y_col].max()) / 2
        total = len(df)
        if total == 0:
            return None
        quadrants = {
            "upper_left": ((df[x_col] < x_mid) & (df[y_col] >= y_mid)).sum(),
            "upper_right": ((df[x_col] >= x_mid) & (df[y_col] >= y_mid)).sum(),
            "lower_left": ((df[x_col] < x_mid) & (df[y_col] < y_mid)).sum(),
            "lower_right": ((df[x_col] >= x_mid) & (df[y_col] < y_mid)).sum(),
        }
        return {k: round(v / total, 2) for k, v in quadrants.items()}

    def _render_assets(self, plan, ai_elements, export_target: str,
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
                                       "bbox": panel["bbox"], "panel_id": panel["panel_id"],
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
                    self._safe_gen_ai, panel, el,
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
                               "bbox": panel["bbox"], "panel_id": panel["panel_id"],
                               "z_order": self._zorder(asset_id, plan)})

        text_placements = self._render_labels(plan, manifest_assets, export_target)
        return manifest_assets, validation_reports, placements, text_placements

    def _safe_gen_ai(self, panel, el, pre_rendered_meta=None):
        try:
            path = self.run_dir / "assets" / f"{el['element_id']}.png"
            if pre_rendered_meta is not None and Path(pre_rendered_meta["path"]).exists():
                report = self.provider.validate_image_asset(
                    path, physical_size_mm=tuple(panel["physical_size"])
                )
                return (el["element_id"], pre_rendered_meta, report, None)
            meta = self.provider.generate_image_asset(el["prompt"], {}, output_path=path)
            report = self.provider.validate_image_asset(
                path, physical_size_mm=tuple(panel["physical_size"]))
            return (el["element_id"], meta, report, None)
        except Exception as e:  # noqa: BLE001
            return (el["element_id"], None, None, e)

    def _render_labels(self, plan, manifest_assets, export_target: str) -> list[dict]:
        text_placements: list[dict] = []
        for i, label in enumerate(self.request.get("labels", [])):
            asset_id = label["element_id"]
            svg_path = self.run_dir / "vectors" / f"{asset_id}.svg"
            if not svg_path.is_file():
                canvas = SvgCanvas(width=200, height=40)
                canvas.text(2, 16, label["content"], font_size=12, fill="#000000")
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
                    "font_size": 9,
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
