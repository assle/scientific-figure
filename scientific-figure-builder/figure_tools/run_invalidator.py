"""Explicit dependency-aware invalidation plans for run artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

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
                "plans/layout_wireframe.svg",
                "plans/layout_analysis.json",
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
                "plans/layout_wireframe.svg",
                "plans/layout_analysis.json",
                *_EXECUTION_PATHS,
            ),
            cleared_steps=(
                "intake", "planning", "planning_approval", *_EXECUTION_STEPS,
            ),
            cleared_artifacts=("figure_brief", "figure_plan", *_EXECUTION_ARTIFACTS),
        ))

    def after_figure_plan_change(self) -> InvalidationPlan:
        return self.apply(InvalidationPlan(
            removed_paths=(
                "plans/layout_wireframe.svg",
                "plans/layout_analysis.json",
                *_EXECUTION_PATHS,
            ),
            cleared_steps=("planning_approval", *_EXECUTION_STEPS),
            cleared_artifacts=_EXECUTION_ARTIFACTS,
        ))

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
