"""Full figure workflow orchestration (plan sections 4, 9, 10, 11, 15).

Ties together planning, routing, deterministic engines, the (mock) Ark client,
two-layer validation, assembly, final validation, export, and reporting.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from figure_tools.assembly.compositor import compose_assets
from figure_tools.plotting.renderer import render_plot
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.planning.planner import create_figure_plan
from figure_tools.planning.router import classify_task
from figure_tools.report import write_generation_report
from figure_tools.validation.final_checks import validate_assembled_figure
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

    def run(self) -> dict[str, Any]:
        task = classify_task(self.request)
        plan = create_figure_plan(self.request)
        self._write_json("plans/figure_plan.json", plan)
        (self.run_dir / "plans").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "plans" / "layout_wireframe.svg").write_text(
            generate_wireframe(plan), encoding="utf-8")

        # Approval gate: no paid generation without explicit opt-in.
        if plan["approval"]["status"] != "auto_execute":
            self.state.request_approval("plan_approval", "pending")
            return {"paused": True, "pause_reason": "plan_approval",
                    "figure_plan": plan, "task": task}

        # Style-anchor gate: >=3 AI assets -> generate one anchor, then pause.
        ai_elements = [
            (panel, el)
            for panel in self.request["panels"]
            for el in panel.get("elements", [])
            if el["type"] == "image_asset"
        ]
        if len(ai_elements) >= 3:
            panel, el = ai_elements[0]
            self.ark.generate_image_asset(
                el["prompt"], {}, output_path=self.run_dir / "assets" / f"{el['element_id']}.png")
            self.state.request_approval("style_anchor_approval", "pending")
            return {"paused": True, "pause_reason": "style_anchor_approval",
                    "figure_plan": plan, "task": task}

        manifest_assets: list[dict] = []
        validation_reports: list[dict] = []
        placements: list[dict] = []
        text_placements: list[dict] = []

        for panel in self.request["panels"]:
            for el in panel.get("elements", []):
                asset_id = el["element_id"]
                try:
                    if el["type"] == "data_plot":
                        spec = load_plot_spec(el["plot_spec"])
                        out = self.run_dir / "plots" / asset_id
                        render_plot(spec, output_dir=out, base_dir=self.base_dir)
                        path = out / "plot.png"
                        manifest_assets.append(self._raster_meta(asset_id, "data_plot",
                                                                  path, plan, transparent=False))
                        placements.append({"path": str(path), "bbox": panel["bbox"],
                                           "z_order": self._zorder(asset_id, plan)})
                    elif el["type"] == "image_asset":
                        path = self.run_dir / "assets" / f"{asset_id}.png"
                        meta = self.ark.generate_image_asset(
                            el["prompt"], {}, output_path=path)
                        report = self.ark.validate_image_asset(
                            path, physical_size_mm=tuple(panel["physical_size"]))
                        validation_reports.append(report)
                        manifest_assets.append(self._raster_meta(
                            asset_id, "image_asset", path, plan,
                            transparent=meta["transparent"]))
                        placements.append({"path": str(path), "bbox": panel["bbox"],
                                           "z_order": self._zorder(asset_id, plan)})
                except Exception as e:  # noqa: BLE001
                    validation_reports.append({
                        "schema_version": "1.0", "run_id": asset_id,
                        "checks": [{"check_id": "render", "scope": f"asset:{asset_id}",
                                    "level": "error", "status": "fail", "detail": str(e)}],
                        "summary": {"errors": 1, "warnings": 0, "passed": 0, "blocking": True},
                    })

        # Labels as SVG vector elements.
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

        manifest = {"schema_version": "1.0", "assets": manifest_assets}
        self._write_json("asset_manifest.json", manifest)

        # Assemble.
        assembly_dir = self.run_dir / "assembly"
        compose_assets(placements, output_dir=assembly_dir, canvas_mm=self._canvas_mm(),
                       dpi=self.compose_dpi, text_placements=text_placements)
        composed_png = assembly_dir / "figure.png"

        # Final validation.
        final = validate_assembled_figure(plan, manifest, composed_png,
                                          physical_size_mm=self._canvas_mm(),
                                          run_id=self.state.run_id)
        validation_reports.append(final)

        exported = False
        if not final["summary"]["blocking"]:
            exports = self.run_dir / "exports"
            exports.mkdir(parents=True, exist_ok=True)
            for ext in ("png", "svg", "pdf"):
                src = assembly_dir / f"figure.{ext}"
                if src.exists():
                    shutil.copyfile(src, exports / f"figure.{ext}")
            exported = True

        self.state.save(self.run_dir / "run_state.json")
        report_path = write_generation_report(
            self.run_dir, plan, manifest, validation_reports,
            run_state=self.state.to_dict(), exported=exported)

        return {
            "paused": False,
            "task": task,
            "figure_plan": plan,
            "asset_manifest": manifest,
            "validation_reports": validation_reports,
            "exported": exported,
            "report_path": str(report_path),
        }

    def _zorder(self, asset_id: str, plan: dict) -> int:
        for a in plan["assets"]:
            if a["asset_id"] == asset_id:
                return a["z_order"]
        return 0

    def _raster_meta(self, asset_id, atype, path, plan, transparent):
        from PIL import Image
        import hashlib
        img = Image.open(path)
        return {
            "asset_id": asset_id, "type": atype, "path": str(path),
            "content_hash": "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "pixel_dimensions": list(img.size), "transparent": transparent,
            "z_order": self._zorder(asset_id, plan),
            "validation_result": {"status": "pass"},
            "parent_asset_id": None,
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
            "parent_asset_id": None,
        }
