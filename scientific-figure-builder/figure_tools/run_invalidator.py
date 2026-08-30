"""Explicit dependency-aware invalidation plans for run artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from figure_tools.provenance import hash_file
from figure_tools.run_store import RunStore
from figure_tools.state import RunState


@dataclass(frozen=True)
class InvalidationPlan:
    removed_paths: tuple[str, ...]
    cleared_steps: tuple[str, ...]
    cleared_artifacts: tuple[str, ...]


_EXECUTION_PATHS = (
    "plans/execution_result.json",
    "plans/repair_plan.json",
    "plans/export_result.json",
    "asset_manifest.json",
    "generation_report.md",
    "validation",
    "assembly",
    "plots",
    "vectors",
    "assets",
    "exports",
)

_PLANNING_DERIVED_PATHS = (
    "plans/layout_wireframe.svg",
    "plans/layout_analysis.json",
    "plans/figure_graph.json",
    "plans/solved_layout.json",
    "plans/figure_blueprint.svg",
    "plans/structure_questions.json",
    "plans/generation_conditions.json",
)

_EXECUTION_STEPS = ("execution", "review_and_repair", "export")
_EXECUTION_ARTIFACTS = (
    "execution_result",
    "validation_report",
    "export_result",
    "exports",
)


class RunInvalidator:
    """Compute and apply exact invalidation plans for one run."""

    def __init__(self, run_dir: str | Path, state: RunState) -> None:
        self.store = RunStore(run_dir)
        self.state = state

    def after_figure_brief_change(self) -> InvalidationPlan:
        return self.apply(InvalidationPlan(
            removed_paths=(
                "plans/figure_plan.json",
                *_PLANNING_DERIVED_PATHS,
                *_EXECUTION_PATHS,
            ),
            cleared_steps=("planning", "planning_approval", *_EXECUTION_STEPS),
            cleared_artifacts=("figure_plan", *_EXECUTION_ARTIFACTS),
        ))

    def for_clarification_submission(self) -> InvalidationPlan:
        return self.apply(InvalidationPlan(
            removed_paths=(
                "plans/figure_brief.json",
                "plans/request.json",
                "plans/figure_plan.json",
                *_PLANNING_DERIVED_PATHS,
                *_EXECUTION_PATHS,
            ),
            cleared_steps=(
                "intake", "planning", "planning_approval", *_EXECUTION_STEPS,
            ),
            cleared_artifacts=("figure_brief", "figure_plan", *_EXECUTION_ARTIFACTS),
        ))

    def after_figure_plan_change(
        self,
        previous_plan: Mapping[str, Any],
        current_plan: Mapping[str, Any],
    ) -> InvalidationPlan:
        removed = [
            *_PLANNING_DERIVED_PATHS,
            "plans/execution_result.json",
            "plans/repair_plan.json",
            "plans/export_result.json",
            "asset_manifest.json",
            "generation_report.md",
            "validation",
            "assembly",
            "exports",
        ]
        previous_assets = self._plan_assets(previous_plan)
        current_assets = self._plan_assets(current_plan)
        changed_ids = {
            asset_id
            for asset_id in previous_assets.keys() | current_assets.keys()
            if self._generation_signature(previous_assets.get(asset_id))
            != self._generation_signature(current_assets.get(asset_id))
        }
        previous_target = (previous_plan.get("delivery") or {}).get("export_target")
        current_target = (current_plan.get("delivery") or {}).get("export_target")
        if previous_target != current_target:
            changed_ids.update(
                asset_id
                for asset_id, asset in {**previous_assets, **current_assets}.items()
                if asset.get("type") != "image_asset"
            )
        for asset_id in sorted(changed_ids):
            asset = current_assets.get(asset_id) or previous_assets.get(asset_id) or {}
            removed.append(self._asset_output_path(asset_id, asset))
        removed_paths = tuple(dict.fromkeys(removed))
        return self.apply(InvalidationPlan(
            removed_paths=removed_paths,
            cleared_steps=("planning_approval", *_EXECUTION_STEPS),
            cleared_artifacts=_EXECUTION_ARTIFACTS,
        ))

    @staticmethod
    def _plan_assets(plan: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        return {
            str(asset["asset_id"]): asset
            for asset in plan.get("assets", [])
            if isinstance(asset, Mapping) and asset.get("asset_id")
        }

    @staticmethod
    def _generation_signature(asset: Mapping[str, Any] | None) -> Any:
        if asset is None:
            return None
        placement_only = {"z_order", "dependencies", "panel_id", "bbox", "physical_size"}
        return {
            key: value for key, value in asset.items() if key not in placement_only
        }

    @staticmethod
    def _asset_output_path(asset_id: str, asset: Mapping[str, Any]) -> str:
        asset_type = asset.get("type")
        if asset_type == "data_plot":
            return f"plots/{asset_id}"
        if asset_type == "image_asset":
            return f"assets/{asset_id}.png"
        return f"vectors/{asset_id}.svg"

    def after_repairs(self, repaired_routes: Mapping[str, str]) -> InvalidationPlan:
        paths = [
            "plans/execution_result.json",
            "plans/repair_plan.json",
            "plans/export_result.json",
            "asset_manifest.json",
            "generation_report.md",
            "validation",
            "assembly",
            "exports",
        ]
        for asset_id, route in sorted(repaired_routes.items()):
            if route == "python":
                paths.extend((f"plots/{asset_id}", "plans/layout_analysis.json"))
            elif route == "svg":
                paths.append(f"vectors/{asset_id}.svg")
            elif route in {"layout_patch", "connector_patch"}:
                paths.extend(_PLANNING_DERIVED_PATHS)
            elif route != "image_edit":
                raise ValueError(f"unknown repair route: {route}")
        return self.apply(InvalidationPlan(
            removed_paths=tuple(dict.fromkeys(paths)),
            cleared_steps=_EXECUTION_STEPS,
            cleared_artifacts=_EXECUTION_ARTIFACTS,
        ))

    def after_assembly_change(self) -> InvalidationPlan:
        return self.apply(InvalidationPlan(
            removed_paths=(
                "plans/execution_result.json",
                "plans/repair_plan.json",
                "plans/export_result.json",
                "validation",
                "exports",
            ),
            cleared_steps=_EXECUTION_STEPS,
            cleared_artifacts=_EXECUTION_ARTIFACTS,
        ))

    def after_corrupt_execution(
        self, manifest: Mapping[str, object] | None,
    ) -> InvalidationPlan:
        paths = [
            "plans/execution_result.json",
            "plans/repair_plan.json",
            "plans/export_result.json",
            "validation",
            "exports",
        ]
        assets = (manifest or {}).get("assets", [])
        if isinstance(assets, list):
            for asset in assets:
                if not isinstance(asset, Mapping):
                    continue
                path = Path(str(asset.get("path", "")))
                if path.is_file() and asset.get("content_hash") == hash_file(path):
                    continue
                asset_id = str(asset.get("asset_id", ""))
                asset_type = asset.get("type")
                if asset_type == "data_plot":
                    paths.append(f"plots/{asset_id}")
                elif asset_type in {
                    "text", "label", "annotation", "equation", "vector_element",
                }:
                    paths.append(f"vectors/{asset_id}.svg")
                elif asset_type == "image_asset":
                    try:
                        paths.append(str(path.relative_to(self.store.run_dir)))
                    except ValueError:
                        continue
        return self.apply(InvalidationPlan(
            removed_paths=tuple(dict.fromkeys(paths)),
            cleared_steps=_EXECUTION_STEPS,
            cleared_artifacts=_EXECUTION_ARTIFACTS,
        ))

    def for_export_rerun(self) -> InvalidationPlan:
        return self.apply(InvalidationPlan(
            removed_paths=("plans/export_result.json", "exports"),
            cleared_steps=("export",),
            cleared_artifacts=("export_result", "exports"),
        ))

    def apply(self, plan: InvalidationPlan) -> InvalidationPlan:
        for step in plan.cleared_steps:
            self.state.clear_step(step)
        for artifact in plan.cleared_artifacts:
            self.state.clear_artifact(artifact)
        for relative in plan.removed_paths:
            self.store.delete(relative)
        self.store.ensure_structure()
        return plan


__all__ = ["InvalidationPlan", "RunInvalidator"]
