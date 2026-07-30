"""Full figure workflow orchestration (plan sections 4, 9, 10, 11, 15).

Ties together planning, routing, deterministic engines, the (mock) Ark client,
two-layer validation, assembly, final validation, export, and reporting.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from figure_tools.assembly.compositor import compose_assets
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.planning.layout_analysis import analyze_layout
from figure_tools.planning.planner import create_figure_plan
from figure_tools.planning.router import classify_task
from figure_tools.report import write_generation_report
from figure_tools.validation.final_checks import validate_assembled_figure
from figure_tools.validation.root_cause import analyze_root_causes
from figure_tools.vector.primitives import SvgCanvas
from figure_tools.vector.wireframe import generate_wireframe


class FigureWorkflow:
    def __init__(
        self,
        request: dict[str, Any],
        config: dict[str, Any],
        run_dir: str | Path,
        ark_client: Any,
        state: Any,
        base_dir: str | Path = ".",
        compose_dpi: int = 300,
    ) -> None:
        self.request = request
        self.config = config
        self.run_dir = Path(run_dir)
        self.ark = ark_client
        self.state = state
        self.base_dir = Path(base_dir)
        self.compose_dpi = compose_dpi

    def _write_json(self, rel: str, data: dict) -> Path:
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def _canvas_mm(self) -> tuple[float, float]:
        c = self.request["canvas"]
        return float(c["width"]), float(c["height"])

    def run(self, approved: bool = False,
            style_anchor_approved: bool = False,
            force_export: bool = False) -> dict[str, Any]:
        task = classify_task(self.request)
        plan = create_figure_plan(self.request)
        self._write_json("plans/figure_plan.json", plan)
        (self.run_dir / "plans").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "plans" / "layout_wireframe.svg").write_text(
            generate_wireframe(plan), encoding="utf-8")

        # Pre-render layout analysis (spec 0001, improvement 2).
        data_chars = self._collect_data_characteristics()
        layout_report = analyze_layout(plan, data_chars)
        self._write_json("plans/layout_analysis.json", layout_report)

        # Persist style bible and inputs (plan section 13).
        self._write_style_bible()
        self._copy_inputs()

        # Approval gate: no paid generation without explicit opt-in (section 4).
        if plan["approval"]["status"] != "auto_execute" and not approved:
            self.state.request_approval("plan_approval", "pending")
            return {"paused": True, "pause_reason": "plan_approval",
                    "figure_plan": plan, "task": task}
        self.state.request_approval("plan_approval", "approved")

        # Style-anchor gate (section 4 step 10): >=3 AI assets.
        ai_elements = [
            (panel, el)
            for panel in self.request["panels"]
            for el in panel.get("elements", [])
            if el["type"] == "image_asset"
        ]
        if len(ai_elements) >= 3:
            anchor_id = ai_elements[0][1]["element_id"]
            anchor_path = self.run_dir / "assets" / f"{anchor_id}.png"
            if not anchor_path.exists():
                self.ark.generate_image_asset(
                    ai_elements[0][1]["prompt"], {}, output_path=anchor_path)
            if not style_anchor_approved:
                self.state.request_approval("style_anchor_approval", "pending")
                return {"paused": True, "pause_reason": "style_anchor_approval",
                        "figure_plan": plan, "task": task}
            self.state.request_approval("style_anchor_approval", "approved")

        manifest_assets, validation_reports, placements, text_placements = \
            self._render_assets(plan, ai_elements)

        manifest = {"schema_version": "1.0", "assets": manifest_assets}
        self._write_json("asset_manifest.json", manifest)

        # Assemble.
        assembly_dir = self.run_dir / "assembly"
        assembly_result = compose_assets(placements, output_dir=assembly_dir,
                                         canvas_mm=self._canvas_mm(),
                                         dpi=self.compose_dpi,
                                         text_placements=text_placements)
        composed_png = Path(assembly_result["files"]["png"])

        # Final validation (plan section 17.1): thread the ark client and the
        # assembly layout manifest so the multimodal final check actually runs.
        final = validate_assembled_figure(
            figure_plan=plan,
            asset_manifest=manifest,
            composed_image_path=composed_png,
            physical_size_mm=self._canvas_mm(),
            run_id=self.state.run_id,
            layout_manifest_path=assembly_result.get("layout_manifest"),
            ark_client=self.ark,
            qa_config=self.config.get("validation", {}),
        )
        validation_reports.append(final)
        self._write_json("validation/validation_report.json", final)

        # Export gate (spec 0001, improvement 3).
        exported = False
        export_blocked_reason: str | None = None
        if not validation_reports:
            export_blocked_reason = (
                "no validation reports found; run validation before export"
            )
        elif not force_export and any(r["summary"]["blocking"] for r in validation_reports):
            export_blocked_reason = (
                "validation reports contain blocking errors; "
                "use force_export=True to override"
            )
        else:
            exports = self.run_dir / "exports"
            exports.mkdir(parents=True, exist_ok=True)
            for ext in ("png", "svg", "pdf"):
                src = assembly_dir / f"figure.{ext}"
                if src.exists():
                    shutil.copyfile(src, exports / f"figure.{ext}")
            exported = True

        # Root cause analysis (spec 0001, improvement 4).
        has_failures = any(
            any(c.get("status") == "fail" for c in r.get("checks", []))
            for r in validation_reports
        )
        if has_failures:
            root_cause = analyze_root_causes(validation_reports, plan, layout_report)
            self._write_json("validation/root_cause_report.json", root_cause)

        self.state.save(self.run_dir / "run_state.json")
        report_path = write_generation_report(
            self.run_dir, plan, manifest, validation_reports,
            run_state=self.state.to_dict(), exported=exported,
            force_export=force_export, export_blocked_reason=export_blocked_reason)

        return {
            "paused": False,
            "task": task,
            "figure_plan": plan,
            "asset_manifest": manifest,
            "validation_reports": validation_reports,
            "exported": exported,
            "export_blocked_reason": export_blocked_reason,
            "report_path": str(report_path),
        }

    def _zorder(self, asset_id: str, plan: dict) -> int:
        for a in plan["assets"]:
            if a["asset_id"] == asset_id:
                return a["z_order"]
        return 0

    def _write_style_bible(self) -> None:
        from figure_tools._resources import template_path

        src = template_path("default-style-bible.json")
        (self.run_dir / "style_bible.json").write_text(src.read_text(encoding="utf-8"),
                                                        encoding="utf-8")

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

    def _render_assets(self, plan, ai_elements):
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
                    render_plot(spec, output_dir=out, base_dir=self.base_dir)
                    path = out / "plot.png"
                    manifest_assets.append(
                        self._local_meta(asset_id, "data_plot", path, plan, transparent=False))
                    placements.append({"asset_id": asset_id, "path": str(path),
                                       "bbox": panel["bbox"],
                                       "z_order": self._zorder(asset_id, plan)})
                except Exception as e:  # noqa: BLE001
                    validation_reports.append(self._error_report(asset_id, str(e)))

        # AI assets: independent, concurrency 2 (plan section 12).
        ai_results: dict[str, tuple] = {}
        if ai_elements:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = {ex.submit(self._safe_gen_ai, panel, el): el["element_id"]
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
                               "bbox": panel["bbox"],
                               "z_order": self._zorder(asset_id, plan)})

        text_placements = self._render_labels(plan, manifest_assets)
        return manifest_assets, validation_reports, placements, text_placements

    def _safe_gen_ai(self, panel, el):
        try:
            path = self.run_dir / "assets" / f"{el['element_id']}.png"
            meta = self.ark.generate_image_asset(el["prompt"], {}, output_path=path)
            report = self.ark.validate_image_asset(
                path, physical_size_mm=tuple(panel["physical_size"]))
            return (el["element_id"], meta, report, None)
        except Exception as e:  # noqa: BLE001
            return (el["element_id"], None, None, e)

    def _render_labels(self, plan, manifest_assets) -> list[dict]:
        text_placements: list[dict] = []
        for i, label in enumerate(self.request.get("labels", [])):
            asset_id = label["element_id"]
            svg_path = self.run_dir / "vectors" / f"{asset_id}.svg"
            svg_path.parent.mkdir(parents=True, exist_ok=True)
            canvas = SvgCanvas(width=200, height=40)
            canvas.text(2, 16, label["content"], font_size=12, fill="#000000")
            svg_path.write_text(canvas.to_string(), encoding="utf-8")
            manifest_assets.append(self._vector_meta(asset_id, "text", svg_path, plan))
            panel = self.request["panels"][i] if i < len(self.request["panels"]) else None
            if panel is not None:
                text_placements.append({"x": panel["bbox"][0] + 0.02,
                                        "y": panel["bbox"][1] + 0.02,
                                        "text": label["content"], "font_size": 9})
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
            "content_hash": "sha256:" + hashlib.sha256(
                Path(path).read_bytes()).hexdigest(),
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
        from figure_tools.ark.client import file_hash

        return {
            "asset_id": asset_id, "type": atype, "path": str(path),
            "content_hash": file_hash(path),
            "pixel_dimensions": [int(self._canvas_mm()[0] / 25.4 * self.compose_dpi),
                                 int(self._canvas_mm()[1] / 25.4 * self.compose_dpi)],
            "transparent": True, "z_order": self._zorder(asset_id, plan),
            "validation_result": {"status": "pass"},
            "provenance": {"endpoint_id": "svg", "seed": None, "timestamp": self._now()},
            "parent_asset_id": None,
        }
