"""Planning-owned derivation of graph, layout, style, and generation conditions."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from figure_tools.figure_graph import build_figure_graph
from figure_tools.figure_layout import solve_figure_layout
from figure_tools.generation_conditions import compile_generation_condition
from figure_tools.planning.geometry import resolve_asset_bbox
from figure_tools.planning.layout_analysis import analyze_layout
from figure_tools.plotting.spec import load_plot_spec
from figure_tools.provenance import hash_file, hash_json
from figure_tools.provider_configuration import provider_capabilities_for_role
from figure_tools.publication_profiles import get_publication_profile
from figure_tools.run_store import RunStore
from figure_tools.validation.graph_structure import build_structure_questions
from figure_tools.vector.blueprint import render_figure_blueprint
from figure_tools.vector.wireframe import generate_wireframe


class FigurePlanningArtifacts:
    """Derive every no-cost artifact owned by Planning behind one Interface."""

    def __init__(
        self,
        request: dict[str, Any],
        config: dict[str, Any],
        run_dir: str | Path,
        provider_client: Any,
        *,
        base_dir: str | Path = ".",
    ) -> None:
        self.request = request
        self.config = config
        self.store = RunStore(run_dir)
        self.run_dir = Path(run_dir)
        self.provider = provider_client
        self.base_dir = Path(base_dir)

    def prepare(self, plan: dict[str, Any]) -> dict[str, Any]:
        self._write_style_bible()
        self.refresh_graph(plan)
        self.refresh_generation_conditions(plan)
        layout_report = self.refresh_layout_analysis(plan)
        self._copy_inputs()
        self._commit_plan(plan)
        return layout_report

    def refresh_after_repairs(
        self,
        plan: dict[str, Any],
        repaired_routes: Mapping[str, str],
    ) -> None:
        routes = set(repaired_routes.values())
        if "connector_patch" in routes:
            self.refresh_graph(plan)
        elif "layout_patch" in routes:
            self.refresh_layout(plan)
        if "python" in routes:
            self.refresh_layout_analysis(plan)
        self._commit_plan(plan)

    def refresh_graph(self, plan: dict[str, Any]) -> None:
        graph = build_figure_graph(self.request, plan)
        graph_reference = self.store.commit_json(
            "plans/figure_graph.json", graph, schema="figure-graph.schema.json"
        )
        questions_reference = self.store.commit_json(
            "plans/structure_questions.json",
            {
                "schema_version": "1.0",
                "figure_id": graph["figure_id"],
                "questions": build_structure_questions(graph),
            },
            schema="structure-questions.schema.json",
        )
        plan["figure_graph_ref"] = self._artifact_ref(
            "plans/figure_graph.json", graph_reference
        )
        plan["structure_questions_ref"] = self._artifact_ref(
            "plans/structure_questions.json", questions_reference
        )
        self.refresh_layout(plan, graph=graph)

    def refresh_layout(
        self,
        plan: dict[str, Any],
        *,
        graph: dict[str, Any] | None = None,
    ) -> None:
        graph = graph or self.store.load_json(
            "plans/figure_graph.json", schema="figure-graph.schema.json"
        )
        panels = {str(item["panel_id"]): item for item in plan.get("panels", [])}
        hints = {
            str(asset["asset_id"]): resolve_asset_bbox(
                asset, panels[str(asset["panel_id"])]
            )
            for asset in plan.get("assets", [])
            if asset.get("panel_id") and asset.get("bbox")
        }
        solved_layout = solve_figure_layout(graph, plan["canvas"], hints)
        layout_reference = self.store.commit_json(
            "plans/solved_layout.json",
            solved_layout,
            schema="solved-layout.schema.json",
        )
        blueprint_reference = self.store.commit_text(
            "plans/figure_blueprint.svg", render_figure_blueprint(solved_layout)
        )
        plan["solved_layout_ref"] = self._artifact_ref(
            "plans/solved_layout.json", layout_reference
        )
        plan["blueprint_ref"] = self._artifact_ref(
            "plans/figure_blueprint.svg", blueprint_reference
        )
        self.store.commit_text("plans/layout_wireframe.svg", generate_wireframe(plan))

    def refresh_generation_conditions(
        self,
        plan: dict[str, Any],
        *,
        style_anchors: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        style_path = self.run_dir / "style_bible.json"
        style_bible = json.loads(style_path.read_text(encoding="utf-8"))
        profile_id = str(
            self.request.get("publication_profile")
            or self.config.get("publication_profile")
            or "general"
        )
        publication_profile = get_publication_profile(profile_id)
        capabilities = provider_capabilities_for_role(
            "image_generate",
            self.config.get("models") or {},
            self.config.get("providers") or {},
            adapter_capabilities=(
                self.provider.generation_capabilities()
                if hasattr(self.provider, "generation_capabilities")
                else {}
            ),
        )
        style_group_counts: dict[str, int] = {}
        for asset in plan.get("assets", []):
            if asset.get("type") != "image_asset":
                continue
            source = asset.get("source") or {}
            group = str(source.get("style_group") or "figure")
            style_group_counts[group] = style_group_counts.get(group, 0) + 1
        repeated_groups = sorted(
            group for group, count in style_group_counts.items() if count > 1
        )
        if repeated_groups and not capabilities.get("supports_reference_image", False):
            raise ValueError(
                "Style groups with multiple raster assets require "
                "supports_reference_image: " + ", ".join(repeated_groups)
            )
        conditions = []
        for asset in plan.get("assets", []):
            if asset.get("type") != "image_asset":
                continue
            source = dict(asset.get("source") or {})
            references = self._verified_references(source.get("references", []))
            style_group = str(source.get("style_group") or "figure")
            anchor = (style_anchors or {}).get(style_group)
            if anchor is not None and asset["asset_id"] != anchor["asset_id"]:
                references.append({
                    "role": "style",
                    "path": str(anchor["path"]),
                    "content_hash": str(anchor["content_hash"]),
                    "strength": 1.0,
                })
            conditions.append(compile_generation_condition({
                "asset_id": asset["asset_id"],
                "model_role": "image_generate",
                "scientific_intent": self.request.get("intent", ""),
                "prompt": source.get("prompt", ""),
                "style_bible": style_bible,
                "style_bible_hash": hash_file(style_path),
                "publication_profile": publication_profile,
                "publication_profile_hash": hash_json(publication_profile),
                "parameters": source.get("parameters", {}),
                "references": references,
                "provider_capabilities": capabilities,
            }))
        artifact = {"schema_version": "1.0", "conditions": conditions}
        reference = self.store.commit_json(
            "plans/generation_conditions.json",
            artifact,
            schema="generation-conditions.schema.json",
        )
        plan["generation_conditions_ref"] = self._artifact_ref(
            "plans/generation_conditions.json", reference
        )
        return artifact

    def refresh_layout_analysis(self, plan: dict[str, Any]) -> dict[str, Any]:
        report = analyze_layout(plan, self._collect_data_characteristics())
        self.store.commit_json("plans/layout_analysis.json", report)
        return report

    def _verified_references(self, references: Any) -> list[dict[str, Any]]:
        verified = []
        for raw in references or []:
            if not isinstance(raw, Mapping):
                raise ValueError("every asset reference must be an object")
            item = dict(raw)
            path = Path(str(item.get("path") or ""))
            if not path.is_file():
                raise ValueError(f"asset reference is missing: {path}")
            actual_hash = hash_file(path)
            supplied_hash = str(item.get("content_hash") or "")
            if supplied_hash and supplied_hash != actual_hash:
                raise ValueError(f"asset reference hash mismatch: {path}")
            item["content_hash"] = actual_hash
            verified.append(item)
        return verified

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
        source = template_path("default-style-bible.json")
        self.store.commit_json(
            "style_bible.json", json.loads(source.read_text(encoding="utf-8"))
        )

    def _copy_inputs(self) -> None:
        inputs = self.run_dir / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        references = [*self.request.get("reference_figures", [])]
        references.extend(
            item["path"]
            for panel in self.request.get("panels", [])
            for element in panel.get("elements", [])
            for item in element.get("references", [])
        )
        for reference in dict.fromkeys(str(item) for item in references):
            source = Path(reference)
            if source.exists():
                shutil.copyfile(source, inputs / source.name)
        for panel in self.request["panels"]:
            for element in panel.get("elements", []):
                if element["type"] != "data_plot":
                    continue
                try:
                    spec = load_plot_spec(element["plot_spec"])
                    source = self.base_dir / spec.source_data["path"]
                    if source.exists():
                        shutil.copyfile(source, inputs / source.name)
                except Exception:  # noqa: BLE001
                    pass

    def _collect_data_characteristics(self) -> dict[str, Any]:
        panels: dict[str, Any] = {}
        labels = self.request.get("labels", [])
        for index, panel in enumerate(self.request["panels"]):
            panel_id = panel["panel_id"]
            element_count = 0
            label_length = 0
            densities = {
                "upper_left": 0.3, "upper_right": 0.3,
                "lower_left": 0.3, "lower_right": 0.3,
            }
            for element in panel.get("elements", []):
                element_count += 1
                if element["type"] != "data_plot":
                    continue
                try:
                    spec = load_plot_spec(element["plot_spec"])
                    element_count += max(len(spec.series) - 1, 0)
                    for value in spec.labels.values():
                        label_length = max(label_length, len(str(value)))
                    computed = self._compute_density(spec)
                    if computed:
                        densities = computed
                except Exception:  # noqa: BLE001
                    pass
            if index < len(labels):
                label_length = max(label_length, len(labels[index].get("content", "")))
            panels[panel_id] = {
                "data_element_count": element_count,
                "label_text_length": label_length,
                "data_density_by_region": densities,
            }
        return {"panels": panels}

    def _compute_density(self, spec) -> dict[str, float] | None:
        import pandas as pd

        data_path = self.base_dir / spec.source_data["path"]
        if not data_path.exists():
            return None
        data = pd.read_csv(data_path)
        x_column = spec.column_mapping.get("x", "")
        y_column = spec.column_mapping.get("y", "")
        if x_column not in data.columns or y_column not in data.columns:
            return None
        x_mid = (data[x_column].min() + data[x_column].max()) / 2
        y_mid = (data[y_column].min() + data[y_column].max()) / 2
        total = len(data)
        if total == 0:
            return None
        quadrants = {
            "upper_left": ((data[x_column] < x_mid) & (data[y_column] >= y_mid)).sum(),
            "upper_right": ((data[x_column] >= x_mid) & (data[y_column] >= y_mid)).sum(),
            "lower_left": ((data[x_column] < x_mid) & (data[y_column] < y_mid)).sum(),
            "lower_right": ((data[x_column] >= x_mid) & (data[y_column] < y_mid)).sum(),
        }
        return {key: round(value / total, 2) for key, value in quadrants.items()}

    def _commit_plan(self, plan: dict[str, Any]) -> None:
        self.store.commit_json(
            "plans/figure_plan.json", plan, schema="figure-plan.schema.json"
        )

    @staticmethod
    def _artifact_ref(path: str, reference: Mapping[str, Any]) -> dict[str, Any]:
        return {"artifact": path, "content_hash": reference["content_hash"]}


__all__ = ["FigurePlanningArtifacts"]
