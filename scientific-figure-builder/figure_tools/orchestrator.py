"""Step orchestrator with resume and incremental invalidation (plan section 15).

Phase 3 exit criteria:
- An interrupted deterministic run resumes without repeating completed work.
- Local edits invalidate only affected downstream artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from figure_tools.state import RunState
from figure_tools.lifecycle_prompts import (
    PHASE_PROMPT_VERSION,
    prompt_for,
)
from figure_tools.phase_workers import StructuredPhaseWorker


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


class FigureOrchestrator:
    """Single public lifecycle seam for figure runs.

    The initial implementation deliberately delegates rendering to the existing
    ``FigureWorkflow``. The seam owns phase results and worker context now, so
    later slices can move each deterministic operation behind the same contract
    without changing Calling Agent behavior.
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
        if action_name == "apply_repair":
            self._apply_repair(action_data)
            return self.advance("resume")
        if action_name == "submit_clarifications":
            self._apply_clarifications(action_data)
            action_name = "resume"

        brief = self._load_json("plans/figure_brief.json")
        if brief is None:
            brief = self._intake()
        if brief["status"] != "ready":
            return self._paused(
                "intake", "submit_clarifications",
                clarifications=brief["required_clarifications"],
                artifacts={"figure_brief": self._artifact_ref("plans/figure_brief.json")},
            )
        self.state.mark_step("intake", "completed", {
            "figure_brief": self._hash_json(brief),
        })

        plan = self._load_json("plans/figure_plan.json")
        if plan is None:
            plan = self._planning(brief)
        else:
            expected_brief_hash = self._hash_json(brief)
            actual_brief_hash = (plan.get("brief_ref") or {}).get("content_hash")
            if actual_brief_hash and actual_brief_hash != expected_brief_hash:
                self._next_plan_revision = int(plan.get("revision", 1)) + 1
                self._invalidate_plan_downstream()
                plan = self._planning(brief)
        self.state.mark_step("planning", "completed", {
            "figure_plan": self._hash_json(plan),
        })
        self._record_artifact("figure_brief", "plans/figure_brief.json")
        self._record_artifact("figure_plan", "plans/figure_plan.json")

        if (action_name in (None, "start", "resume")
                and self.state.step_status("export") == "completed"
                and (self.run_dir / "exports").exists()):
            return self._completed_result()

        plan_approved = self.state.step_status("planning_approval") == "completed"
        if action_name == "approve_plan":
            self.state.mark_step("planning_approval", "completed", {
                "figure_plan": self._hash_json(plan),
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
                    "figure_brief": self._artifact_ref("plans/figure_brief.json"),
                    "figure_plan": self._artifact_ref("plans/figure_plan.json"),
                },
            )
        self.state.request_approval("plan_approval", "approved")

        from figure_tools.workflow import FigureWorkflow

        workflow = FigureWorkflow(
            self.request, self.config, self.run_dir, self.provider, self.state,
            base_dir=self.base_dir, compose_dpi=self.compose_dpi,
        )
        existing_execution = self._existing_execution()
        if existing_execution is not None:
            execution_result, execution = existing_execution
        else:
            layout_path = self.run_dir / "plans" / "layout_analysis.json"
            layout_report = (json.loads(layout_path.read_text(encoding="utf-8"))
                             if layout_path.is_file() else {})
            pre_rendered_assets = self._load_json("plans/pre_rendered_assets.json") or {}
            execution = workflow.execute_plan(
                plan, export_target=self._export_target(),
                style_anchor_approved=(action_name == "approve_style_anchor"),
                layout_report=layout_report,
                pre_rendered_assets=pre_rendered_assets,
            )
            if execution.get("paused"):
                if execution.get("pause_reason") == "style_anchor_approval":
                    self.state.mark_step("execution", "pending")
                    return self._paused(
                        "execution", "approve_style_anchor",
                        artifacts={
                            "figure_brief": self._artifact_ref("plans/figure_brief.json"),
                            "figure_plan": self._artifact_ref("plans/figure_plan.json"),
                        },
                    )
                return self._paused("execution", execution.get("pause_reason", "continue"))

            execution_result = self._write_execution_result(execution, plan)
            pre_rendered_path = self.run_dir / "plans" / "pre_rendered_assets.json"
            if pre_rendered_path.exists():
                pre_rendered_path.unlink()
            self.state.mark_step("execution", "completed", {
                "execution_result": self._hash_json(execution_result),
            })
            self._record_artifact("execution_result", "plans/execution_result.json")
        validation_reports = execution.get("validation_reports", [])
        if self.state.step_status("review_and_repair") == "completed":
            pending_repair = self._load_json("plans/repair_plan.json")
            if pending_repair is not None:
                review_kind = "repair_plan"
                review_artifact: Mapping[str, Any] | None = pending_repair
            else:
                review_kind = "validation_report"
                review_artifact = self._load_json("validation/final.json")
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
            self._validate_artifact(review_artifact, "validation-report.schema.json")
            self._write_json("validation/final.json", review_artifact)
            self._write_json("validation/validation_report.json", review_artifact)
        elif review_kind == "repair_plan":
            self._validate_artifact(review_artifact, "repair-plan.schema.json")
            self._write_json("plans/repair_plan.json", review_artifact)
        else:
            raise ValueError(f"unknown Review and repair artifact kind: {review_kind}")
        self.state.mark_step("review_and_repair", "completed", {
            "validation_report": self._hash_json(validation_reports[-1])
            if validation_reports else "",
        })
        self._record_artifact("validation_report", "validation/final.json")

        if review_kind == "repair_plan" and action_name != "force_export":
            return self._paused(
                "review_and_repair", "repair_required",
                artifacts={
                    "execution_result": self._artifact_ref("plans/execution_result.json"),
                    "validation_report": self._artifact_ref("validation/final.json"),
                    "repair_plan": self._artifact_ref("plans/repair_plan.json"),
                },
            )

        published = workflow.publish(
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
                artifacts={"validation_report": self._artifact_ref("validation/final.json")},
                export_blocked_reason=published["export_blocked_reason"],
            )
        self._write_export_result(
            published,
            forced=(action_name == "force_export"),
            reason=(str(action_data["reason"])
                    if action_name == "force_export" else None),
        )
        self.state.mark_step("export", "completed", {
            "exports": self._hash_paths("exports"),
        })
        if action_name == "force_export":
            self.state.record_audit("force_export", {"reason": str(action_data["reason"])})
        self.state.mark_phase("export")
        self._record_artifact("exports", "exports")
        self._record_artifact("export_result", "plans/export_result.json")
        self.state.save(self.run_dir / "run_state.json")
        return {
            "phase": "export",
            "status": "completed",
            "next_action": None,
            "artifacts": {
                "figure_brief": self._artifact_ref("plans/figure_brief.json"),
                "figure_plan": self._artifact_ref("plans/figure_plan.json"),
                "execution_result": self._artifact_ref("plans/execution_result.json"),
                "validation_report": self._artifact_ref("validation/final.json"),
                "export_result": self._artifact_ref("plans/export_result.json"),
                "exports": self._artifact_ref("exports"),
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
        answers = action.get("answers")
        if not isinstance(answers, Mapping) or not answers:
            raise ValueError("submit_clarifications requires a non-empty answers object")
        allowed = {"export_target", "figure_width_cm", "language", "style"}
        unknown = sorted(set(answers) - allowed)
        if unknown:
            raise ValueError(f"unknown clarification fields: {', '.join(unknown)}")
        draft = self._load_json("plans/figure_brief.json")
        if draft is not None and draft.get("status") != "draft":
            raise ValueError("clarifications can only update a draft Figure brief")
        self.request.update(dict(answers))
        for rel in ("plans/figure_brief.json", "plans/request.json"):
            path = self.run_dir / rel
            if path.exists():
                path.unlink()
        self.state.clear_step("intake")
        self.state.clear_artifact("figure_brief")

    def _intake(self) -> dict[str, Any]:
        brief = dict(self._invoke_worker(
            "intake",
            {
                "user_request": json.loads(json.dumps(self.request, default=str)),
                "run_id": self.state.run_id,
                "prompt_hash": self._prompt_hash("intake"),
            },
            ("check_figure_requirements",),
        ))
        self._validate_artifact(brief, "figure-brief.schema.json")
        request_snapshot = dict(brief["request"])
        clarifications = list(brief["required_clarifications"])
        self._write_json("plans/figure_brief.json", brief)
        self._write_json("plans/request.json", request_snapshot)
        self.state.mark_step("intake", "completed" if not clarifications else "pending", {
            "figure_brief": self._hash_json(brief),
        })
        self.state.request_approval(
            "clarification", "approved" if not clarifications else "pending",
        )
        self.state.save(self.run_dir / "run_state.json")
        return brief

    def _planning(self, brief: dict[str, Any]) -> dict[str, Any]:
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
        self._validate_artifact(plan, "figure-plan.schema.json")
        request = self.request
        request.update(brief.get("delivery") or {})
        request["language"] = brief.get("language")
        request["style"] = brief.get("style")
        request["canvas"] = plan["canvas"]
        request["brief_ref"] = plan["brief_ref"]
        from figure_tools.workflow import FigureWorkflow
        workflow = FigureWorkflow(
            request, self.config, self.run_dir, self.provider, self.state,
            base_dir=self.base_dir, compose_dpi=self.compose_dpi,
        )
        workflow.prepare_plan_artifacts(plan)
        self._write_json(f"plans/figure_plan.v{plan.get('revision', 1)}.json", plan)
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
        self._write_json(f"prompts/{phase}.json", {
            "phase": phase,
            "prompt_version": invocation.prompt_version,
            "prompt_hash": self._prompt_hash(phase),
            "allowed_tools": list(invocation.allowed_tools),
        })
        (self.run_dir / "prompts" / f"{phase}.txt").write_text(
            invocation.prompt, encoding="utf-8",
        )
        return self.worker.run(invocation)

    def _write_execution_result(self, result: Mapping[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        reports = result.get("validation_reports", [])
        execution = {
            "schema_version": "1.0",
            "artifact_type": "execution_result",
            "run_id": self.state.run_id,
            "plan_ref": {
                "artifact": "plans/figure_plan.json",
                "content_hash": self._hash_json(plan),
            },
            "status": "completed",
            "asset_manifest": self._artifact_ref("asset_manifest.json"),
            "plots": self._artifact_ref("plots"),
            "vectors": self._artifact_ref("vectors"),
            "assembly": self._artifact_ref("assembly"),
            "layout_manifests": [
                self._artifact_ref(str(path.relative_to(self.run_dir)))
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
        self._validate_artifact(execution, "execution-result.schema.json")
        self._write_json("plans/execution_result.json", execution)
        return execution

    def _force_export_existing(
        self, plan: dict[str, Any], reason: str,
    ) -> dict[str, Any]:
        manifest = self._load_json("asset_manifest.json")
        final = self._load_json("validation/final.json")
        if manifest is None or final is None or not (self.run_dir / "assembly").exists():
            raise ValueError("cannot force export without an existing execution result")
        from figure_tools.workflow import FigureWorkflow
        published = FigureWorkflow(
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
                artifacts={"validation_report": self._artifact_ref("validation/final.json")},
                export_blocked_reason=published["export_blocked_reason"],
            )
        self._write_export_result(published, forced=True, reason=reason)
        self.state.mark_step("export", "completed", {"exports": self._hash_paths("exports")})
        self.state.record_audit("force_export", {"reason": reason})
        self.state.mark_phase("export")
        self._record_artifact("figure_brief", "plans/figure_brief.json")
        self._record_artifact("figure_plan", "plans/figure_plan.json")
        self._record_artifact("execution_result", "plans/execution_result.json")
        self._record_artifact("validation_report", "validation/final.json")
        self._record_artifact("exports", "exports")
        self._record_artifact("export_result", "plans/export_result.json")
        self.state.save(self.run_dir / "run_state.json")
        return {
            "phase": "export", "status": "completed", "next_action": None,
            "artifacts": {
                "figure_brief": self._artifact_ref("plans/figure_brief.json"),
                "figure_plan": self._artifact_ref("plans/figure_plan.json"),
                "execution_result": self._artifact_ref("plans/execution_result.json"),
                "validation_report": self._artifact_ref("validation/final.json"),
                "export_result": self._artifact_ref("plans/export_result.json"),
                "exports": self._artifact_ref("exports"),
            },
        }

    def _record_artifact(self, name: str, rel: str) -> None:
        self.state.set_artifact(name, self._artifact_ref(rel))

    def _write_export_result(
        self, published: Mapping[str, Any], *, forced: bool,
        reason: str | None,
    ) -> dict[str, Any]:
        validation = self._load_json("validation/final.json") or {}
        artifact = {
            "schema_version": "1.0",
            "artifact_type": "export_result",
            "run_id": self.state.run_id,
            "validation_ref": {
                "artifact": "validation/final.json",
                "content_hash": self._hash_json(validation),
            },
            "assembly_ref": self._artifact_ref("assembly"),
            "files": dict(published.get("files", {})),
            "forced": forced,
            "reason": reason,
        }
        self._validate_artifact(artifact, "export-result.schema.json")
        self._write_json("plans/export_result.json", artifact)
        return artifact

    def _existing_execution(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if self.state.step_status("execution") != "completed":
            return None
        execution_result = self._load_json("plans/execution_result.json")
        manifest = self._load_json("asset_manifest.json")
        if (execution_result is None or manifest is None
                or not (self.run_dir / "assembly").is_dir()
                or not (self.run_dir / "validation" / "final.json").is_file()):
            return None
        return execution_result, {
            "paused": False,
            "manifest": manifest,
            "validation_reports": list(execution_result.get("validation_reports", [])),
        }

    def _completed_result(self) -> dict[str, Any]:
        self.state.mark_phase("export")
        self.state.save(self.run_dir / "run_state.json")
        return {
            "phase": "export", "status": "completed", "next_action": None,
            "artifacts": {
                "figure_brief": self._artifact_ref("plans/figure_brief.json"),
                "figure_plan": self._artifact_ref("plans/figure_plan.json"),
                "execution_result": self._artifact_ref("plans/execution_result.json"),
                "validation_report": self._artifact_ref("validation/final.json"),
                "export_result": self._artifact_ref("plans/export_result.json"),
                "exports": self._artifact_ref("exports"),
            },
        }

    def _invalidate_plan_downstream(self) -> None:
        for step in ("planning", "planning_approval", "execution", "review_and_repair", "export"):
            self.state.clear_step(step)
        for artifact in ("figure_plan", "execution_result", "validation_report", "export_result", "exports"):
            self.state.clear_artifact(artifact)
        for rel in (
            "plans/figure_plan.json", "plans/layout_analysis.json",
            "plans/execution_result.json", "plans/repair_plan.json",
            "plans/export_result.json",
            "asset_manifest.json", "generation_report.md", "validation",
            "assembly", "plots", "vectors", "assets", "exports",
        ):
            path = self.run_dir / rel
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        from figure_tools.state import RunDirectory
        RunDirectory.ensure_structure(self.run_dir)

    def _apply_repair(self, action: Mapping[str, Any]) -> None:
        repairs = action.get("repairs")
        if not isinstance(repairs, list) or not repairs:
            raise ValueError("apply_repair requires a non-empty repairs list")
        plan = self._load_json("plans/figure_plan.json")
        if plan is None:
            raise ValueError("cannot repair without a Figure plan")
        repair_plan = self._load_json("plans/repair_plan.json")
        if repair_plan is None:
            raise ValueError("cannot repair without a Repair plan")
        expected_plan_hash = self._hash_json(plan)
        if (repair_plan.get("plan_ref") or {}).get("content_hash") != expected_plan_hash:
            raise ValueError("Repair plan references a different Figure plan")
        execution_result = self._load_json("plans/execution_result.json")
        validation_report = self._load_json("validation/final.json")
        if execution_result is None or validation_report is None:
            raise ValueError("Repair plan requires Execution and Validation artifacts")
        if ((repair_plan.get("execution_ref") or {}).get("content_hash")
                != self._hash_json(execution_result)):
            raise ValueError("Repair plan references a different Execution result")
        if ((repair_plan.get("validation_ref") or {}).get("content_hash")
                != self._hash_json(validation_report)):
            raise ValueError("Repair plan references a different Validation report")
        elements = {
            el["element_id"]: el
            for panel in self.request.get("panels", [])
            for el in panel.get("elements", [])
        }
        plan_assets = {asset["asset_id"]: asset for asset in plan.get("assets", [])}
        allowed = {item.get("asset_id") for item in repair_plan.get("repairs", [])}
        repaired_routes: dict[str, str] = {}
        for item in repairs:
            if not isinstance(item, Mapping):
                raise ValueError("each repair must be an object")
            asset_id = item.get("asset_id")
            route = item.get("route")
            if asset_id not in allowed or asset_id not in elements:
                raise ValueError(f"asset {asset_id!r} is not in the Repair plan")
            element = elements[asset_id]
            self.state.record_retry(f"repair:{asset_id}", "quality")
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
                manifest = self._load_json("asset_manifest.json")
                manifest_asset = next(
                    (asset for asset in (manifest or {}).get("assets", [])
                     if asset.get("asset_id") == asset_id),
                    None,
                )
                parent_path = Path(manifest_asset["path"]) if manifest_asset else None
                if parent_path is None or not parent_path.is_file():
                    raise ValueError(f"cannot edit missing raster asset {asset_id!r}")
                prompt = item.get("prompt")
                if not isinstance(prompt, str) or not prompt:
                    plan_item = next(
                        entry for entry in repair_plan.get("repairs", [])
                        if entry.get("asset_id") == asset_id
                    )
                    prompt = plan_item.get("action")
                if not isinstance(prompt, str) or not prompt:
                    raise ValueError("image_edit repair requires prompt")
                meta = self.provider.edit_image_asset(
                    parent_path, prompt, {}, output_path=parent_path,
                    parent_asset_id=asset_id,
                )
                pre_rendered = self._load_json("plans/pre_rendered_assets.json") or {}
                pre_rendered[asset_id] = meta
                self._write_json("plans/pre_rendered_assets.json", pre_rendered)
            else:
                raise ValueError(f"asset {asset_id!r} is not repairable")
        self._validate_artifact(plan, "figure-plan.schema.json")
        plan["revision"] = int(plan.get("revision", 1)) + 1
        plan["plan_id"] = f"{plan['figure_id']}-plan-v{plan['revision']}"
        self._validate_artifact(plan, "figure-plan.schema.json")
        self._write_json("plans/figure_plan.json", plan)
        self._write_json(f"plans/figure_plan.v{plan['revision']}.json", plan)
        self.state.mark_step("planning", "completed", {
            "figure_plan": self._hash_json(plan),
        })
        self._record_artifact("figure_plan", "plans/figure_plan.json")
        self._write_json("plans/request.json", json.loads(json.dumps(self.request, default=str)))
        self._invalidate_downstream(repaired_routes)

    def _invalidate_downstream(self, repaired_routes: Mapping[str, str]) -> None:
        for step in ("execution", "review_and_repair", "export"):
            self.state.clear_step(step)
        for artifact in ("execution_result", "validation_report", "export_result", "exports"):
            self.state.clear_artifact(artifact)
        for rel in (
            "plans/execution_result.json", "plans/repair_plan.json",
            "plans/export_result.json",
            "asset_manifest.json", "generation_report.md", "validation",
            "assembly", "exports",
        ):
            path = self.run_dir / rel
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        for asset_id, route in repaired_routes.items():
            if route == "python":
                path = self.run_dir / "plots" / asset_id
                if path.exists():
                    import shutil
                    shutil.rmtree(path)
                layout_path = self.run_dir / "plans" / "layout_analysis.json"
                if layout_path.exists():
                    layout_path.unlink()
            elif route == "svg":
                path = self.run_dir / "vectors" / f"{asset_id}.svg"
                if path.exists():
                    path.unlink()
        from figure_tools.state import RunDirectory
        RunDirectory.ensure_structure(self.run_dir)

    def _required_clarifications(self) -> list[dict[str, Any]]:
        from figure_tools.planning.planner import collect_required_clarifications
        return collect_required_clarifications(self.request or {})

    def _export_target(self) -> str:
        from figure_tools.vector.svg_normalize import resolve_export_target
        value = (self.request or {}).get("export_target")
        if not value:
            value = (self.config.get("export") or {}).get("export_target")
        return resolve_export_target(value)

    def _data_sources(self) -> list[str]:
        from figure_tools.plotting.spec import load_plot_spec
        sources: list[str] = []
        for panel in (self.request or {}).get("panels", []):
            for element in panel.get("elements", []):
                if element.get("type") != "data_plot":
                    continue
                try:
                    sources.append(str(load_plot_spec(element["plot_spec"]).source_data["path"]))
                except Exception:  # noqa: BLE001
                    continue
        return sources

    def _load_request_from_brief(self) -> dict[str, Any] | None:
        request_path = self.run_dir / "plans" / "request.json"
        if request_path.is_file():
            request = json.loads(request_path.read_text(encoding="utf-8"))
            if isinstance(request, dict):
                return request
        brief = self._load_json("plans/figure_brief.json")
        request = brief.get("request") if brief else None
        return request if isinstance(request, dict) else None

    def _load_json(self, rel: str) -> dict[str, Any] | None:
        path = self.run_dir / rel
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def _write_json(self, rel: str, data: Mapping[str, Any]) -> Path:
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def _write_style_bible(self) -> None:
        from figure_tools._resources import template_path
        path = self.run_dir / "style_bible.json"
        if not path.exists():
            path.write_text(template_path("default-style-bible.json").read_text(encoding="utf-8"),
                            encoding="utf-8")

    def _paused(self, phase: str, next_action: str, **extra: Any) -> dict[str, Any]:
        self.state.mark_phase(phase)
        self.state.save(self.run_dir / "run_state.json")
        return {"phase": phase, "status": "paused", "next_action": next_action,
                "artifacts": extra.pop("artifacts", {}), **extra}

    def _artifact_ref(self, rel: str) -> dict[str, Any]:
        path = self.run_dir / rel
        content_hash = self._hash_path(path) if path.is_file() else None
        if path.is_dir():
            content_hash = self._hash_paths(rel)
        return {"path": str(path), "exists": path.exists(),
                "content_hash": content_hash}

    def _hash_path(self, path: Path) -> str | None:
        if not path.is_file():
            return None
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def _hash_json(self, value: Any) -> str:
        payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def _hash_paths(self, rel: str) -> str:
        root = self.run_dir / rel
        paths = sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []
        return self._hash_json({str(p.relative_to(self.run_dir)): self._hash_path(p) for p in paths})

    def _validate_artifact(self, data: Mapping[str, Any], schema_name: str) -> None:
        from jsonschema import Draft202012Validator
        from figure_tools._resources import schema_path

        schema = json.loads(schema_path(schema_name).read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(data),
                        key=lambda error: list(error.path))
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise ValueError(f"invalid {schema_name}: {detail}")

    def _prompt_hash(self, phase: str) -> str:
        return self._hash_json({
            "phase": phase,
            "prompt": prompt_for(phase),
            "version": PHASE_PROMPT_VERSION,
        })


@dataclass
class Step:
    name: str
    fn: Callable[["StepRunner"], dict | None]
    depends_on: list[str] = field(default_factory=list)


class StepRunner:
    def __init__(self, state: RunState, run_dir: str | Path,
                 state_path: str | Path | None = None) -> None:
        self.state = state
        self.run_dir = Path(run_dir)
        self.state_path = Path(state_path) if state_path else None

    def _save(self) -> None:
        if self.state_path:
            self.state.save(self.state_path)

    def _downstream(self, from_step: str, steps: list[Step]) -> list[str]:
        deps = {s.name: list(s.depends_on) for s in steps}
        dependents: set[str] = set()
        changed = True
        while changed:
            changed = False
            for name, ds in deps.items():
                if name in dependents or name == from_step:
                    continue
                if any(d in dependents or d == from_step for d in ds):
                    dependents.add(name)
                    changed = True
        return sorted(dependents)

    def invalidate_from(self, from_step: str, steps: list[Step]) -> None:
        """Clear a step and all of its transitive downstream steps."""
        for name in [from_step, *self._downstream(from_step, steps)]:
            self.state.clear_step(name)
        self.state.set_resume(from_step, invalidate_downstream=True)
        self._save()

    def run(self, steps: list[Step]) -> None:
        for step in steps:
            if self.state.is_completed(step.name):
                continue
            result = step.fn(self)
            output_hashes = result or {}
            self.state.mark_step(step.name, "completed", output_hashes)
            self._save()
