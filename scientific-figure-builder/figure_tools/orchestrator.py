"""Single lifecycle Orchestrator with resume and precise invalidation.

Phase 3 exit criteria:
- An interrupted deterministic run resumes without repeating completed work.
- Local edits invalidate only affected downstream artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any, Mapping, Protocol, Sequence

from figure_tools.state import RunState
from figure_tools.lifecycle_prompts import (
    PHASE_PROMPT_VERSION,
    prompt_for,
)
from figure_tools.imaging.edit_validation import evaluate_local_edit
from figure_tools.phase_workers import StructuredPhaseWorker
from figure_tools.planning.artifacts import FigurePlanningArtifacts
from figure_tools.provenance import hash_file
from figure_tools.run_invalidator import RunInvalidator
from figure_tools.run_store import RunStore


PHASES = ("intake", "planning", "execution", "review_and_repair", "export")
STRING_ACTIONS = frozenset({"start", "resume", "approve_plan", "approve_style_anchor"})
OBJECT_ACTIONS = frozenset({"submit_clarifications", "apply_repair", "force_export"})


@dataclass(frozen=True)
class PhaseInvocation:
    """The narrow context crossing from the orchestrator to a phase worker."""

    phase: str
    prompt: str
    prompt_version: str
    context: Mapping[str, Any]
    allowed_tools: tuple[str, ...]


class PhaseWorker(Protocol):
    def run(self, invocation: PhaseInvocation) -> Mapping[str, Any]:
        """Return a schema-shaped phase suggestion without changing run state."""
        ...


class FigureOrchestrator:
    """Single public lifecycle seam for figure runs.

    Phase transitions, approvals, retries, resume state, and Export gate state
    belong here. Approved production work is delegated to ``FigureExecution``.
    """

    def __init__(
        self,
        request: dict[str, Any] | None,
        config: dict[str, Any],
        run_dir: str | Path,
        provider_client: Any,
        state: RunState,
        base_dir: str | Path = ".",
        compose_dpi: int = 300,
        worker: PhaseWorker | None = None,
    ) -> None:
        self.request = request
        self.config = config
        self.run_dir = Path(run_dir)
        self.provider = provider_client
        self.state = state
        self.base_dir = Path(base_dir)
        self.compose_dpi = compose_dpi
        self.worker = worker or StructuredPhaseWorker()
        self.store = RunStore(self.run_dir)
        self.store.ensure_structure()
        self.invalidator = RunInvalidator(self.run_dir, self.state)
        self._next_plan_revision = 1

    def advance(self, action: str | Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Advance one run until the next user decision or completion.

        ``action`` is intentionally small: ``approve_plan`` and
        ``approve_style_anchor`` resume a paused run; ``force_export`` is an
        explicit export override. All other sequencing belongs to this module.
        """
        action_name, action_data = self._normalize_action(action)
        if self.request is None:
            self.request = self._load_request_from_brief()
        if self.request is None:
            raise ValueError("request is required to start a figure run")
        assert self.request is not None
        if action_name == "apply_repair":
            accepted_edits = self._apply_repair(action_data)
            result = self.advance("resume")
            if accepted_edits and self._global_validation_regressed(accepted_edits):
                self._rollback_accepted_edits(accepted_edits)
                return self.advance("resume")
            for edit in accepted_edits:
                Path(edit["backup_path"]).unlink(missing_ok=True)
            return result
        if action_name == "submit_clarifications":
            self._apply_clarifications(action_data)
            action_name = "resume"

        brief = self.store.load_optional_json("plans/figure_brief.json")
        if brief is None:
            brief = self._intake()
        if brief["status"] != "ready":
            return self._paused(
                "intake", "submit_clarifications",
                clarifications=brief["required_clarifications"],
                artifacts={"figure_brief": self.store.reference("plans/figure_brief.json")},
            )
        self.state.mark_step("intake", "completed", {
            "figure_brief": self.store.hash_json(brief),
        })

        plan = self.store.load_optional_json("plans/figure_plan.json")
        if plan is None:
            plan = self._planning(brief)
        else:
            expected_brief_hash = self.store.hash_json(brief)
            actual_brief_hash = (plan.get("brief_ref") or {}).get("content_hash")
            if actual_brief_hash and actual_brief_hash != expected_brief_hash:
                self._next_plan_revision = int(plan.get("revision", 1)) + 1
                self.invalidator.after_figure_brief_change()
                plan = self._planning(brief)
            else:
                recorded_plan_hash = self.state.output_hashes("planning").get(
                    "figure_plan"
                )
                current_plan_hash = self.store.hash_json(plan)
                if recorded_plan_hash and recorded_plan_hash != current_plan_hash:
                    previous_plan = self._plan_snapshot(recorded_plan_hash)
                    if previous_plan is None:
                        raise ValueError(
                            "cannot reconcile a revised Figure plan without its revision snapshot"
                        )
                    previous_revision = int(previous_plan.get("revision", 1))
                    if int(plan.get("revision", previous_revision)) <= previous_revision:
                        plan["revision"] = previous_revision + 1
                        plan["plan_id"] = (
                            f"{plan['figure_id']}-plan-v{plan['revision']}"
                        )
                    self.store.validate(plan, "figure-plan.schema.json")
                    reusable = self._reusable_raster_assets(
                        self.store.load_optional_json("asset_manifest.json")
                    )
                    if reusable:
                        self.store.commit_json(
                            "plans/pre_rendered_assets.json", reusable
                        )
                    self.invalidator.after_figure_plan_change(previous_plan, plan)
                    FigurePlanningArtifacts(
                        self.request,
                        self.config,
                        self.run_dir,
                        self.provider,
                        base_dir=self.base_dir,
                    ).prepare(plan)
                    self.store.commit_json(
                        f"plans/figure_plan.v{plan['revision']}.json", plan
                    )
        self.state.mark_step("planning", "completed", {
            "figure_plan": self.store.hash_json(plan),
        })
        self._record_artifact("figure_brief", "plans/figure_brief.json")
        self._record_artifact("figure_plan", "plans/figure_plan.json")

        if (
            action_name in (None, "start", "resume")
            and self.state.step_status("export") == "completed"
        ):
            if self._completed_artifacts_current(plan):
                return self._completed_result()
            self._reconcile_stale_completion(plan)

        plan_approved = self.state.step_status("planning_approval") == "completed"
        if action_name == "approve_plan":
            self.state.mark_step("planning_approval", "completed", {
                "figure_plan": self.store.hash_json(plan),
            })
            plan_approved = True
        elif action_name not in (None, "start", "resume", "approve_style_anchor", "force_export"):
            raise ValueError(f"unknown orchestrator action: {action_name}")

        if (action_name == "force_export"
                and self.state.step_status("execution") == "completed"
                and self.state.step_status("review_and_repair") == "completed"):
            return self._force_export_existing(plan, str(action_data["reason"]))

        if not self.request.get("auto_execute") and not plan_approved:
            self.state.request_approval("plan_approval", "pending")
            return self._paused(
                "planning", "approve_plan",
                artifacts={
                    "figure_brief": self.store.reference("plans/figure_brief.json"),
                    "figure_plan": self.store.reference("plans/figure_plan.json"),
                },
            )
        self.state.request_approval("plan_approval", "approved")

        from figure_tools.execution import FigureExecution

        execution_module = FigureExecution(
            self.request, self.config, self.run_dir, self.provider, self.state,
            base_dir=self.base_dir, compose_dpi=self.compose_dpi,
        )
        existing_execution = self._existing_execution(plan)
        if existing_execution is not None:
            execution_result, execution = existing_execution
        else:
            layout_report = (
                self.store.load_optional_json("plans/layout_analysis.json") or {}
            )
            pre_rendered_assets = self.store.load_optional_json("plans/pre_rendered_assets.json") or {}
            execution = execution_module.execute_plan(
                plan, export_target=self._export_target(),
                style_anchor_approved=(action_name == "approve_style_anchor"),
                layout_report=layout_report,
                pre_rendered_assets=pre_rendered_assets,
            )
            if execution.get("paused"):
                if execution.get("pause_reason") == "style_anchor_approval":
                    self.state.request_approval("style_anchor_approval", "pending")
                    self.state.mark_step("execution", "pending")
                    return self._paused(
                        "execution", "approve_style_anchor",
                        artifacts={
                            "figure_brief": self.store.reference("plans/figure_brief.json"),
                            "figure_plan": self.store.reference("plans/figure_plan.json"),
                        },
                    )
                return self._paused("execution", execution.get("pause_reason", "continue"))

            if action_name == "approve_style_anchor":
                self.state.request_approval("style_anchor_approval", "approved")

            execution_result = self._write_execution_result(execution, plan)
            self.store.delete("plans/pre_rendered_assets.json")
            self.state.mark_step("execution", "completed", {
                "execution_result": self.store.hash_json(execution_result),
            })
            self._record_artifact("execution_result", "plans/execution_result.json")
        validation_reports = execution.get("validation_reports", [])
        if self.state.step_status("review_and_repair") == "completed":
            pending_repair = self.store.load_optional_json("plans/repair_plan.json")
            if pending_repair is not None:
                review_kind = "repair_plan"
                review_artifact: Mapping[str, Any] | None = pending_repair
            else:
                review_kind = "validation_report"
                review_artifact = self.store.load_optional_json("validation/final.json")
        else:
            review_result = dict(self._invoke_worker(
                "review_and_repair",
                {
                    "figure_brief": brief,
                    "figure_plan": plan,
                    "execution_result": execution_result,
                    "validation_reports": validation_reports,
                    "run_id": self.state.run_id,
                },
                ("validate_image_asset", "validate_plot_data", "validate_assembled_figure"),
            ))
            review_kind = review_result.get("kind")
            raw_review_artifact = review_result.get("artifact")
            review_artifact = (
                raw_review_artifact if isinstance(raw_review_artifact, Mapping) else None
            )
        if not isinstance(review_artifact, Mapping):
            raise ValueError("Phase worker returned no Review and repair artifact")
        if review_kind == "validation_report":
            self.store.validate(review_artifact, "validation-report.schema.json")
            self.store.commit_json("validation/final.json", review_artifact)
            self.store.commit_json("validation/validation_report.json", review_artifact)
        elif review_kind == "repair_plan":
            self.store.validate(review_artifact, "repair-plan.schema.json")
            self.store.commit_json("plans/repair_plan.json", review_artifact)
        else:
            raise ValueError(f"unknown Review and repair artifact kind: {review_kind}")
        self.state.mark_step("review_and_repair", "completed", {
            "validation_report": self.store.hash_json(validation_reports[-1])
            if validation_reports else "",
        })
        self._record_artifact("validation_report", "validation/final.json")

        if review_kind == "repair_plan" and action_name != "force_export":
            return self._paused(
                "review_and_repair", "repair_required",
                artifacts={
                    "execution_result": self.store.reference("plans/execution_result.json"),
                    "validation_report": self.store.reference("validation/final.json"),
                    "repair_plan": self.store.reference("plans/repair_plan.json"),
                },
            )

        published = execution_module.publish(
            {
                "plan": plan,
                "export_target": self._export_target(),
            },
            execution,
            force_export=(action_name == "force_export"),
            force_export_reason=(str(action_data["reason"])
                                 if action_name == "force_export" else None),
        )
        if not published["exported"]:
            return self._paused(
                "export", "force_export",
                artifacts={"validation_report": self.store.reference("validation/final.json")},
                export_blocked_reason=published["export_blocked_reason"],
            )
        self._write_export_result(
            published,
            forced=(action_name == "force_export"),
            reason=(str(action_data["reason"])
                    if action_name == "force_export" else None),
        )
        self.state.mark_step("export", "completed", {
            "exports": str(self.store.reference("exports")["content_hash"]),
        })
        if action_name == "force_export":
            self.state.record_audit("force_export", {"reason": str(action_data["reason"])})
        self.state.mark_phase("export")
        self._record_artifact("exports", "exports")
        self._record_artifact("export_result", "plans/export_result.json")
        self._save_state()
        return {
            "phase": "export",
            "status": "completed",
            "next_action": None,
            "artifacts": {
                "figure_brief": self.store.reference("plans/figure_brief.json"),
                "figure_plan": self.store.reference("plans/figure_plan.json"),
                "execution_result": self.store.reference("plans/execution_result.json"),
                "validation_report": self.store.reference("validation/final.json"),
                "export_result": self.store.reference("plans/export_result.json"),
                "exports": self.store.reference("exports"),
            },
        }

    def _normalize_action(
        self, action: str | Mapping[str, Any] | None,
    ) -> tuple[str | None, Mapping[str, Any]]:
        if action is None:
            return None, {}
        if isinstance(action, str):
            if action not in STRING_ACTIONS:
                raise ValueError(f"unknown orchestrator action: {action}")
            return action, {}
        if not isinstance(action, Mapping):
            raise ValueError("unknown orchestrator action: action must be a string or object")
        name = action.get("action")
        if not isinstance(name, str):
            raise ValueError("unknown orchestrator action: missing action")
        if name not in OBJECT_ACTIONS:
            raise ValueError(f"unknown orchestrator action: {name}")
        if name == "force_export":
            reason = action.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("force_export requires a non-empty reason")
        return name, action

    def _apply_clarifications(self, action: Mapping[str, Any]) -> None:
        assert self.request is not None
        answers = action.get("answers")
        if not isinstance(answers, Mapping) or not answers:
            raise ValueError("submit_clarifications requires a non-empty answers object")
        allowed = {"export_target", "figure_width_cm", "language", "style"}
        unknown = sorted(set(answers) - allowed)
        if unknown:
            raise ValueError(f"unknown clarification fields: {', '.join(unknown)}")
        draft = self.store.load_optional_json("plans/figure_brief.json")
        if draft is not None and draft.get("status") != "draft":
            raise ValueError("clarifications can only update a draft Figure brief")
        self.invalidator.for_clarification_submission()
        self.request.update(dict(answers))

    def _intake(self) -> dict[str, Any]:
        assert self.request is not None
        brief = dict(self._invoke_worker(
            "intake",
            {
                "user_request": json.loads(json.dumps(self.request, default=str)),
                "run_id": self.state.run_id,
                "prompt_hash": self._prompt_hash("intake"),
            },
            ("check_figure_requirements",),
        ))
        self.store.validate(brief, "figure-brief.schema.json")
        request_snapshot = dict(brief["request"])
        clarifications = list(brief["required_clarifications"])
        self.store.commit_json("plans/figure_brief.json", brief)
        self.store.commit_json("plans/request.json", request_snapshot)
        self.state.mark_step("intake", "completed" if not clarifications else "pending", {
            "figure_brief": self.store.hash_json(brief),
        })
        self.state.request_approval(
            "clarification", "approved" if not clarifications else "pending",
        )
        self._save_state()
        return brief

    def _planning(self, brief: dict[str, Any]) -> dict[str, Any]:
        assert self.request is not None
        plan = dict(self._invoke_worker(
            "planning",
            {
                "figure_brief": brief,
                "default_canvas": self.config.get("canvas") or None,
                "revision": self._next_plan_revision,
            },
            (
                "analyze_reference_figure", "check_figure_requirements",
                "create_figure_plan", "create_layout_wireframe",
            ),
        ))
        self.store.validate(plan, "figure-plan.schema.json")
        request = self.request
        request.update(brief.get("delivery") or {})
        request["language"] = brief.get("language")
        request["style"] = brief.get("style")
        request["canvas"] = plan["canvas"]
        request["brief_ref"] = plan["brief_ref"]
        FigurePlanningArtifacts(
            request,
            self.config,
            self.run_dir,
            self.provider,
            base_dir=self.base_dir,
        ).prepare(plan)
        self.store.commit_json(f"plans/figure_plan.v{plan.get('revision', 1)}.json", plan)
        self.state.request_approval("plan_approval", "pending")
        return plan

    def _invoke_worker(
        self, phase: str, context: Mapping[str, Any], allowed_tools: Sequence[str],
    ) -> Mapping[str, Any]:
        invocation = PhaseInvocation(
            phase=phase,
            prompt=prompt_for(phase),
            prompt_version=PHASE_PROMPT_VERSION,
            context=context,
            allowed_tools=tuple(allowed_tools),
        )
        self.store.commit_json(f"prompts/{phase}.json", {
            "phase": phase,
            "prompt_version": invocation.prompt_version,
            "prompt_hash": self._prompt_hash(phase),
            "allowed_tools": list(invocation.allowed_tools),
        })
        self.store.commit_text(f"prompts/{phase}.txt", invocation.prompt)
        return self.worker.run(invocation)

    def _write_execution_result(self, result: Mapping[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        reports = result.get("validation_reports", [])
        execution = {
            "schema_version": "1.0",
            "artifact_type": "execution_result",
            "run_id": self.state.run_id,
            "plan_ref": {
                "artifact": "plans/figure_plan.json",
                "content_hash": self.store.hash_json(plan),
            },
            "status": "completed",
            "asset_manifest": self.store.reference("asset_manifest.json"),
            "plots": self.store.reference("plots"),
            "vectors": self.store.reference("vectors"),
            "assembly": self.store.reference("assembly"),
            "layout_manifests": [
                self.store.reference(str(path.relative_to(self.run_dir)))
                for path in sorted(self.run_dir.rglob("layout_manifest.json"))
            ],
            "call_provenance": {
                "counts": dict(self.state.to_dict()["calls"]["counts"]),
                "retries": dict(self.state.to_dict()["retries"]),
                "cache_hits": self.state.cache_hits,
            },
            "validation_reports": reports,
            "failures": [r for r in reports if r.get("summary", {}).get("blocking")],
        }
        self.store.validate(execution, "execution-result.schema.json")
        self.store.commit_json("plans/execution_result.json", execution)
        return execution

    def _force_export_existing(
        self, plan: dict[str, Any], reason: str,
    ) -> dict[str, Any]:
        assert self.request is not None
        manifest = self.store.load_optional_json("asset_manifest.json")
        final = self.store.load_optional_json("validation/final.json")
        if manifest is None or final is None or not (self.run_dir / "assembly").exists():
            raise ValueError("cannot force export without an existing execution result")
        from figure_tools.execution import FigureExecution
        published = FigureExecution(
            self.request, self.config, self.run_dir, self.provider, self.state,
            base_dir=self.base_dir, compose_dpi=self.compose_dpi,
        ).publish(
            {"plan": plan, "export_target": self._export_target()},
            {"manifest": manifest, "validation_reports": [final]},
            force_export=True,
            force_export_reason=reason,
        )
        if not published["exported"]:
            return self._paused(
                "export", "force_export",
                artifacts={"validation_report": self.store.reference("validation/final.json")},
                export_blocked_reason=published["export_blocked_reason"],
            )
        self._write_export_result(published, forced=True, reason=reason)
        self.state.mark_step("export", "completed", {
            "exports": str(self.store.reference("exports")["content_hash"]),
        })
        self.state.record_audit("force_export", {"reason": reason})
        self.state.mark_phase("export")
        self._record_artifact("figure_brief", "plans/figure_brief.json")
        self._record_artifact("figure_plan", "plans/figure_plan.json")
        self._record_artifact("execution_result", "plans/execution_result.json")
        self._record_artifact("validation_report", "validation/final.json")
        self._record_artifact("exports", "exports")
        self._record_artifact("export_result", "plans/export_result.json")
        self._save_state()
        return {
            "phase": "export", "status": "completed", "next_action": None,
            "artifacts": {
                "figure_brief": self.store.reference("plans/figure_brief.json"),
                "figure_plan": self.store.reference("plans/figure_plan.json"),
                "execution_result": self.store.reference("plans/execution_result.json"),
                "validation_report": self.store.reference("validation/final.json"),
                "export_result": self.store.reference("plans/export_result.json"),
                "exports": self.store.reference("exports"),
            },
        }

    def _record_artifact(self, name: str, rel: str) -> None:
        self.state.set_artifact(name, self.store.reference(rel))

    def _write_export_result(
        self, published: Mapping[str, Any], *, forced: bool,
        reason: str | None,
    ) -> dict[str, Any]:
        validation = self.store.load_optional_json("validation/final.json") or {}
        artifact = {
            "schema_version": "1.0",
            "artifact_type": "export_result",
            "run_id": self.state.run_id,
            "validation_ref": {
                "artifact": "validation/final.json",
                "content_hash": self.store.hash_json(validation),
            },
            "assembly_ref": self.store.reference("assembly"),
            "files": dict(published.get("files", {})),
            "forced": forced,
            "reason": reason,
        }
        self.store.validate(artifact, "export-result.schema.json")
        self.store.commit_json("plans/export_result.json", artifact)
        return artifact

    def _existing_execution(
        self, plan: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if self.state.step_status("execution") != "completed":
            return None
        if not self._execution_artifacts_current(plan):
            return None
        execution_result = self.store.load_json(
            "plans/execution_result.json", schema="execution-result.schema.json"
        )
        manifest = self.store.load_json(
            "asset_manifest.json", schema="asset-manifest.schema.json"
        )
        return execution_result, {
            "paused": False,
            "manifest": manifest,
            "validation_reports": list(execution_result.get("validation_reports", [])),
        }

    def _execution_artifacts_current(self, plan: Mapping[str, Any]) -> bool:
        try:
            execution = self.store.load_json(
                "plans/execution_result.json", schema="execution-result.schema.json"
            )
            manifest = self.store.load_json(
                "asset_manifest.json", schema="asset-manifest.schema.json"
            )
            final = self.store.load_json(
                "validation/final.json", schema="validation-report.schema.json"
            )
        except Exception:  # corrupt or missing artifacts are never reusable
            return False
        if (execution.get("plan_ref") or {}).get("content_hash") != self.store.hash_json(plan):
            return False
        references = (
            (execution.get("asset_manifest"), "asset_manifest.json"),
            (execution.get("plots"), "plots"),
            (execution.get("vectors"), "vectors"),
            (execution.get("assembly"), "assembly"),
        )
        if any(not self.store.reference_matches(reference, relative) for reference, relative in references):
            return False
        for reference in execution.get("layout_manifests", []):
            path = Path(str(reference.get("path", "")))
            try:
                relative = path.relative_to(self.run_dir)
            except ValueError:
                return False
            if not self.store.reference_matches(reference, relative):
                return False
        reports = execution.get("validation_reports") or []
        if reports and self.store.hash_json(reports[-1]) != self.store.hash_json(final):
            return False
        return self._manifest_assets_current(manifest)

    def _completed_artifacts_current(self, plan: Mapping[str, Any]) -> bool:
        if not self._execution_artifacts_current(plan):
            return False
        state_artifacts = {
            "figure_brief": "plans/figure_brief.json",
            "figure_plan": "plans/figure_plan.json",
            "execution_result": "plans/execution_result.json",
            "validation_report": "validation/final.json",
            "export_result": "plans/export_result.json",
            "exports": "exports",
        }
        if any(
            not self.store.reference_matches(self.state.artifact(name), relative)
            for name, relative in state_artifacts.items()
        ):
            return False
        try:
            export_result = self.store.load_json(
                "plans/export_result.json", schema="export-result.schema.json"
            )
        except Exception:
            return False
        return (
            self.store.reference_matches(
                export_result.get("validation_ref"), "validation/final.json"
            )
            and self.store.reference_matches(export_result.get("assembly_ref"), "assembly")
        )

    def _reconcile_stale_completion(self, plan: Mapping[str, Any]) -> None:
        if not self._execution_artifacts_current(plan):
            manifest = self.store.load_optional_json("asset_manifest.json")
            reusable = self._reusable_raster_assets(manifest)
            if reusable:
                self.store.commit_json("plans/pre_rendered_assets.json", reusable)
            self.invalidator.after_corrupt_execution(manifest)
            return
        self.invalidator.for_export_rerun()

    @staticmethod
    def _manifest_assets_current(manifest: Mapping[str, Any]) -> bool:
        for asset in manifest.get("assets", []):
            path = Path(str(asset.get("path", "")))
            if not path.is_file() or asset.get("content_hash") != hash_file(path):
                return False
        return True


    def _completed_result(self) -> dict[str, Any]:
        self.state.mark_phase("export")
        self._save_state()
        return {
            "phase": "export", "status": "completed", "next_action": None,
            "artifacts": {
                "figure_brief": self.store.reference("plans/figure_brief.json"),
                "figure_plan": self.store.reference("plans/figure_plan.json"),
                "execution_result": self.store.reference("plans/execution_result.json"),
                "validation_report": self.store.reference("validation/final.json"),
                "export_result": self.store.reference("plans/export_result.json"),
                "exports": self.store.reference("exports"),
            },
        }

    def _apply_repair(self, action: Mapping[str, Any]) -> list[dict[str, Any]]:
        assert self.request is not None
        repairs = action.get("repairs")
        if not isinstance(repairs, list) or not repairs:
            raise ValueError("apply_repair requires a non-empty repairs list")
        plan = self.store.load_optional_json("plans/figure_plan.json")
        if plan is None:
            raise ValueError("cannot repair without a Figure plan")
        repair_plan = self.store.load_optional_json("plans/repair_plan.json")
        if repair_plan is None:
            raise ValueError("cannot repair without a Repair plan")
        expected_plan_hash = self.store.hash_json(plan)
        if (repair_plan.get("plan_ref") or {}).get("content_hash") != expected_plan_hash:
            raise ValueError("Repair plan references a different Figure plan")
        execution_result = self.store.load_optional_json("plans/execution_result.json")
        validation_report = self.store.load_optional_json("validation/final.json")
        if execution_result is None or validation_report is None:
            raise ValueError("Repair plan requires Execution and Validation artifacts")
        if ((repair_plan.get("execution_ref") or {}).get("content_hash")
                != self.store.hash_json(execution_result)):
            raise ValueError("Repair plan references a different Execution result")
        if ((repair_plan.get("validation_ref") or {}).get("content_hash")
                != self.store.hash_json(validation_report)):
            raise ValueError("Repair plan references a different Validation report")
        manifest = self.store.load_optional_json("asset_manifest.json")
        pre_rendered = self._reusable_raster_assets(manifest)
        elements = {
            el["element_id"]: el
            for panel in self.request.get("panels", [])
            for el in panel.get("elements", [])
        }
        plan_assets = {asset["asset_id"]: asset for asset in plan.get("assets", [])}
        allowed = {item.get("asset_id") for item in repair_plan.get("repairs", [])}
        repaired_routes: dict[str, str] = {}
        edit_outcomes: list[tuple[str, dict[str, Any]]] = []
        accepted_edits: list[dict[str, Any]] = []
        for item in repairs:
            if not isinstance(item, Mapping):
                raise ValueError("each repair must be an object")
            asset_id = item.get("asset_id")
            route = item.get("route")
            operation = item.get("operation")
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError("each repair requires a non-empty asset_id")
            if asset_id not in allowed or asset_id not in elements:
                raise ValueError(f"asset {asset_id!r} is not in the Repair plan")
            element = elements[asset_id]
            self.state.record_retry(f"repair:{asset_id}", "quality")
            if operation == "layout_patch":
                bbox = item.get("bbox")
                if (
                    not isinstance(bbox, list)
                    or len(bbox) != 4
                    or any(not isinstance(value, (int, float)) for value in bbox)
                    or any(float(value) < 0 or float(value) > 1 for value in bbox)
                    or float(bbox[2]) <= 0
                    or float(bbox[3]) <= 0
                    or float(bbox[0]) + float(bbox[2]) > 1
                    or float(bbox[1]) + float(bbox[3]) > 1
                ):
                    raise ValueError(
                        "layout_patch requires a normalized [x, y, width, height] bbox"
                    )
                bbox_space = str(item.get("bbox_space") or "panel")
                if bbox_space not in {"panel", "canvas"}:
                    raise ValueError("layout_patch bbox_space must be panel or canvas")
                element["bbox"] = list(bbox)
                plan_assets[asset_id]["bbox"] = list(bbox)
                plan_assets[asset_id]["bbox_space"] = bbox_space
                plan_assets[asset_id].setdefault("source", {})["bbox"] = list(bbox)
                repaired_routes[asset_id] = "layout_patch"
                continue
            if operation == "connector_patch":
                edge_id = item.get("edge_id")
                graph = self.request.get("figure_graph")
                if not isinstance(graph, dict) or not isinstance(edge_id, str):
                    raise ValueError(
                        "connector_patch requires an existing Figure Graph edge_id"
                    )
                edge = next(
                    (
                        candidate for candidate in graph.get("typed_edges", [])
                        if candidate.get("edge_id") == edge_id
                    ),
                    None,
                )
                if edge is None:
                    raise ValueError(f"unknown Figure Graph edge {edge_id!r}")
                for field in (
                    "source_port", "target_port", "direction", "semantic_type"
                ):
                    value = item.get(field)
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"connector_patch requires {field}")
                    edge[field] = value
                repaired_routes[asset_id] = "connector_patch"
                continue
            if operation == "vector_patch":
                route = "svg"
            elif operation == "raster_edit":
                route = "image_edit"
            if not isinstance(route, str):
                raise ValueError("each repair requires a route")
            repaired_routes[str(asset_id)] = str(route)
            if element.get("type") in {"data_plot", "label", "annotation", "text", "equation", "vector_element"}:
                if route == "image_edit":
                    raise ValueError("deterministic assets cannot use image_edit")
                if route not in {"python", "svg"}:
                    raise ValueError(f"invalid deterministic repair route: {route}")
                if element.get("type") == "data_plot":
                    plot_spec = item.get("plot_spec")
                    if not isinstance(plot_spec, str) or not plot_spec:
                        raise ValueError("python repair requires plot_spec")
                    element["plot_spec"] = plot_spec
                    plan_assets[asset_id].setdefault("source", {})["plot_spec"] = plot_spec
                else:
                    content = item.get("content")
                    if not isinstance(content, str) or not content:
                        raise ValueError("svg repair requires content")
                    element["content"] = content
                    plan_assets[asset_id].setdefault("source", {})["content"] = content
                    for text_element in plan.get("text_elements", []):
                        if text_element.get("element_id") == asset_id:
                            text_element["content"] = content
            elif element.get("type") == "image_asset":
                if route != "image_edit":
                    raise ValueError(f"invalid raster repair route: {route}")
                manifest_asset = next(
                    (asset for asset in (manifest or {}).get("assets", [])
                     if asset.get("asset_id") == asset_id),
                    None,
                )
                parent_path = Path(manifest_asset["path"]) if manifest_asset else None
                if parent_path is None or not parent_path.is_file():
                    raise ValueError(f"cannot edit missing raster asset {asset_id!r}")
                repair_item = next(
                    entry for entry in repair_plan.get("repairs", [])
                    if entry.get("asset_id") == asset_id
                )
                prompt = item.get("prompt")
                if not isinstance(prompt, str) or not prompt:
                    prompt = repair_item.get("action")
                if not isinstance(prompt, str) or not prompt:
                    raise ValueError("image_edit repair requires prompt")
                edit_path = (
                    self.run_dir / "assets" / "edits"
                    / f"{asset_id}-v{int(plan.get('revision', 1)) + 1}.png"
                )
                edit_path.parent.mkdir(parents=True, exist_ok=True)
                raw_mask_path = item.get("mask_path")
                mask_path = (
                    Path(raw_mask_path)
                    if isinstance(raw_mask_path, str) and raw_mask_path
                    else None
                )
                meta = self.provider.edit_image_asset(
                    parent_path,
                    prompt,
                    {},
                    output_path=edit_path,
                    parent_asset_id=asset_id,
                    mask_path=mask_path,
                )
                panel = next(
                    (
                        candidate for candidate in self.request.get("panels", [])
                        if any(
                            child.get("element_id") == asset_id
                            for child in candidate.get("elements", [])
                        )
                    ),
                    None,
                )
                physical_size = (
                    (
                        float(panel["physical_size"][0]),
                        float(panel["physical_size"][1]),
                    )
                    if panel is not None
                    else None
                )
                edited_validation = self.provider.validate_image_asset(
                    edit_path, physical_size_mm=physical_size,
                )
                source_check = str(repair_item.get("source_check") or "")

                def source_status(report: Mapping[str, Any]) -> str | None:
                    return next(
                        (
                            str(check.get("status"))
                            for check in report.get("checks", [])
                            if check.get("check_id") == source_check
                        ),
                        None,
                    )

                original_status = source_status(validation_report)
                edited_status = source_status(edited_validation)
                target_improved = (
                    original_status == "fail" and edited_status == "pass"
                )
                outcome = evaluate_local_edit(
                    parent_path,
                    edit_path,
                    mask_path=mask_path,
                    physical_size_mm=physical_size,
                    target_improved=target_improved,
                )
                outcome["target_check"] = source_check or None
                outcome["target_before"] = original_status
                outcome["target_after"] = edited_status
                if outcome["accepted"]:
                    original_meta = dict(pre_rendered.get(asset_id) or {})
                    backup_path = (
                        self.run_dir / "assets" / "edit_backups"
                        / f"{asset_id}-v{int(plan.get('revision', 1))}.png"
                    )
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(parent_path, backup_path)
                    shutil.copyfile(edit_path, parent_path)
                    meta["path"] = str(parent_path)
                    meta["content_hash"] = hash_file(parent_path)
                    meta["condition_hash"] = (
                        manifest_asset or {}
                    ).get("condition_hash")
                    pre_rendered[asset_id] = meta
                    accepted_edits.append({
                        "asset_id": asset_id,
                        "parent_path": str(parent_path),
                        "backup_path": str(backup_path),
                        "original_meta": original_meta,
                        "baseline_validation": validation_report,
                    })
                    status = "accepted"
                else:
                    edit_path.unlink(missing_ok=True)
                    status = "rolled_back"
                edit_outcomes.append((asset_id, {
                        "schema_version": "1.0",
                        "asset_id": asset_id,
                        "status": status,
                        "reason": outcome["reason"],
                        "mask_path": str(mask_path) if mask_path else None,
                        "original_summary": outcome["original_summary"],
                        "edited_summary": outcome["edited_summary"],
                        "unmasked_mean_absolute_difference": outcome[
                            "unmasked_mean_absolute_difference"
                        ],
                        "target_check": outcome["target_check"],
                        "target_before": outcome["target_before"],
                        "target_after": outcome["target_after"],
                    }))
            else:
                raise ValueError(f"asset {asset_id!r} is not repairable")
        self.store.validate(plan, "figure-plan.schema.json")
        plan["revision"] = int(plan.get("revision", 1)) + 1
        plan["plan_id"] = f"{plan['figure_id']}-plan-v{plan['revision']}"
        self.store.validate(plan, "figure-plan.schema.json")
        self.invalidator.after_repairs(repaired_routes)
        rebuild_plan_artifacts = any(
            route in {"python", "layout_patch", "connector_patch"}
            for route in repaired_routes.values()
        )
        if rebuild_plan_artifacts:
            planning_artifacts = FigurePlanningArtifacts(
                self.request,
                self.config,
                self.run_dir,
                self.provider,
                base_dir=self.base_dir,
            )
            planning_artifacts.refresh_after_repairs(plan, repaired_routes)
        else:
            self.store.commit_json(
                "plans/figure_plan.json", plan, schema="figure-plan.schema.json"
            )
        self.store.commit_json(f"plans/figure_plan.v{plan['revision']}.json", plan)
        self.state.mark_step("planning", "completed", {
            "figure_plan": self.store.hash_json(plan),
        })
        self._record_artifact("figure_plan", "plans/figure_plan.json")
        self.store.commit_json(
            "plans/request.json",
            json.loads(json.dumps(self.request, default=str)),
        )
        if pre_rendered:
            self.store.commit_json("plans/pre_rendered_assets.json", pre_rendered)
        for asset_id, outcome in edit_outcomes:
            self.store.commit_json(
                f"validation/edit_outcomes/{asset_id}.json", outcome,
            )
        return accepted_edits

    def _global_validation_regressed(self, edits: list[dict[str, Any]]) -> bool:
        current = self.store.load_optional_json("validation/final.json") or {}
        current_failures = {
            (str(check.get("check_id")), str(check.get("scope"))): check
            for check in current.get("checks", [])
            if check.get("level") == "error" and check.get("status") == "fail"
        }
        for edit in edits:
            baseline = edit.get("baseline_validation") or {}
            baseline_failures = {
                (str(check.get("check_id")), str(check.get("scope")))
                for check in baseline.get("checks", [])
                if check.get("level") == "error" and check.get("status") == "fail"
            }
            if any(key not in baseline_failures for key in current_failures):
                return True
        return False

    def _rollback_accepted_edits(self, edits: list[dict[str, Any]]) -> None:
        reusable: dict[str, dict[str, Any]] = {}
        outcomes: list[tuple[str, dict[str, Any]]] = []
        for edit in edits:
            asset_id = str(edit["asset_id"])
            parent_path = Path(edit["parent_path"])
            backup_path = Path(edit["backup_path"])
            shutil.copyfile(backup_path, parent_path)
            backup_path.unlink(missing_ok=True)
            original_meta = dict(edit.get("original_meta") or {})
            original_meta["path"] = str(parent_path)
            original_meta["content_hash"] = hash_file(parent_path)
            reusable[asset_id] = original_meta
            outcome = self.store.load_optional_json(
                f"validation/edit_outcomes/{asset_id}.json"
            ) or {"schema_version": "1.0", "asset_id": asset_id}
            outcome["status"] = "rolled_back"
            outcome["reason"] = "global validation regressed after raster edit"
            outcomes.append((asset_id, outcome))
        if reusable:
            self.store.commit_json("plans/pre_rendered_assets.json", reusable)
            self.invalidator.after_repairs({
                asset_id: "image_edit" for asset_id in reusable
            })
        for asset_id, outcome in outcomes:
            self.store.commit_json(
                f"validation/edit_outcomes/{asset_id}.json", outcome,
            )

    @staticmethod
    def _reusable_raster_assets(
        manifest: Mapping[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        reusable: dict[str, dict[str, Any]] = {}
        for asset in (manifest or {}).get("assets", []):
            if asset.get("type") != "image_asset":
                continue
            path = Path(str(asset.get("path", "")))
            generation = asset.get("generation") or {}
            if (
                not path.is_file()
                or asset.get("content_hash") != hash_file(path)
                or not isinstance(generation, Mapping)
            ):
                continue
            reusable[str(asset["asset_id"])] = {
                "path": str(path),
                "content_hash": asset.get("content_hash"),
                "model": generation.get("model"),
                "parameters": dict(generation.get("parameters") or {}),
                "prompt_hash": asset.get("prompt_hash"),
                "condition_hash": asset.get("condition_hash"),
                "reference_hashes": list(asset.get("reference_hashes") or []),
                "pixel_dimensions": list(asset.get("pixel_dimensions") or []),
                "transparent": bool(asset.get("transparent")),
                "provenance": dict(asset.get("provenance") or {}),
                "parent_asset_id": asset.get("parent_asset_id"),
            }
        return reusable

    def _export_target(self) -> str:
        from figure_tools.vector.svg_normalize import resolve_export_target
        value = (self.request or {}).get("export_target")
        if not value:
            value = (self.config.get("export") or {}).get("export_target")
        return resolve_export_target(value)

    def _load_request_from_brief(self) -> dict[str, Any] | None:
        request = self.store.load_optional_json("plans/request.json")
        if request is not None:
            return request
        brief = self.store.load_optional_json("plans/figure_brief.json")
        request = brief.get("request") if brief else None
        return request if isinstance(request, dict) else None

    def _plan_snapshot(self, content_hash: str) -> dict[str, Any] | None:
        for path in sorted((self.run_dir / "plans").glob("figure_plan.v*.json")):
            relative = path.relative_to(self.run_dir)
            candidate = self.store.load_optional_json(relative)
            if candidate is not None and self.store.hash_json(candidate) == content_hash:
                return candidate
        return None

    def _paused(self, phase: str, next_action: str, **extra: Any) -> dict[str, Any]:
        self.state.mark_phase(phase)
        self._save_state()
        return {"phase": phase, "status": "paused", "next_action": next_action,
                "artifacts": extra.pop("artifacts", {}), **extra}

    def _save_state(self) -> None:
        self.store.commit_json(
            "run_state.json",
            self.state.to_dict(),
            schema="run-state.schema.json",
        )

    def _prompt_hash(self, phase: str) -> str:
        return self.store.hash_json({
            "phase": phase,
            "prompt": prompt_for(phase),
            "version": PHASE_PROMPT_VERSION,
        })
