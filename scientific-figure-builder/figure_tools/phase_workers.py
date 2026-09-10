"""Phase worker adapters that return schema-governed lifecycle artifacts."""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from figure_tools._resources import schema_path
from figure_tools.provenance import hash_json


class StructuredPhaseWorker:
    """Offline production worker for deterministic phase reasoning.

    It receives only the PhaseInvocation context and returns the artifact for
    that phase. A model-backed adapter can satisfy the same worker interface.
    """

    def run(self, invocation: Any) -> Mapping[str, Any]:
        if invocation.phase == "intake":
            return self._intake(invocation)
        if invocation.phase == "planning":
            return self._planning(invocation)
        if invocation.phase == "review_and_repair":
            return self._review(invocation)
        raise ValueError(f"unsupported worker phase: {invocation.phase}")

    def _intake(self, invocation: Any) -> dict[str, Any]:
        from figure_tools.planning.planner import collect_required_clarifications
        from figure_tools.plotting.spec import load_plot_spec

        request = copy.deepcopy(dict(invocation.context["user_request"]))
        clarifications = collect_required_clarifications(request)
        data_sources: list[str] = []
        for panel in request.get("panels", []):
            for element in panel.get("elements", []):
                if element.get("type") != "data_plot":
                    continue
                try:
                    spec = load_plot_spec(element["plot_spec"])
                    data_sources.append(str(spec.source_data["path"]))
                except Exception:  # noqa: BLE001
                    continue
        run_id = str(invocation.context["run_id"])
        return {
            "schema_version": "1.0",
            "artifact_type": "figure_brief",
            "brief_id": f"{request['figure_id']}-brief-v1",
            "figure_id": request["figure_id"],
            "run_id": run_id,
            "request": request,
            "intent": request.get("intent", request.get("description", "")),
            "inputs": {
                "reference_figures": list(request.get("reference_figures", [])),
                "data_sources": data_sources,
            },
            "delivery": {
                key: request[key]
                for key in ("export_target", "figure_width_cm", "include_pptx")
                if request.get(key) is not None
            },
            "language": request.get("language"),
            "style": request.get("style"),
            "assumptions": list(request.get("assumptions", [])),
            "uncertainties": list(request.get("uncertainties", [])),
            "required_clarifications": clarifications,
            "status": "ready" if not clarifications else "draft",
            "provenance": {
                "phase": "intake",
                "prompt_version": invocation.prompt_version,
                "prompt_hash": str(invocation.context["prompt_hash"]),
                "request_hash": hash_json(request),
            },
        }

    def _planning(self, invocation: Any) -> dict[str, Any]:
        from figure_tools.planning.advice import default_planning_advice

        brief = copy.deepcopy(dict(invocation.context["figure_brief"]))
        if brief.get("status") != "ready":
            raise ValueError("Planning requires a ready Figure brief")
        return default_planning_advice(brief)

    def _review(self, invocation: Any) -> dict[str, Any]:
        plan = dict(invocation.context["figure_plan"])
        execution = dict(invocation.context["execution_result"])
        reports = list(invocation.context["validation_reports"])
        blocking = any(report.get("summary", {}).get("blocking") for report in reports)
        if not blocking:
            artifact = reports[-1] if reports else {
                "schema_version": "1.0",
                "run_id": invocation.context["run_id"],
                "checks": [],
                "summary": {"errors": 0, "warnings": 0, "passed": 0, "blocking": False},
            }
            return {"kind": "validation_report", "artifact": artifact}

        assets_by_id = {asset["asset_id"]: asset for asset in plan.get("assets", [])}
        repairs: list[dict[str, Any]] = []
        for report in reports:
            for check in report.get("checks", []):
                if check.get("status") != "fail":
                    continue
                element_ids = check.get("element_ids") or [
                    asset_id for asset_id in assets_by_id
                    if check.get("scope", "").endswith(asset_id)
                ]
                for asset_id in element_ids:
                    asset = assets_by_id.get(asset_id)
                    if asset is None:
                        continue
                    route = asset.get("routing")
                    if route == "image_model" and not (asset.get("source") or {}).get("generation_unit"):
                        route = "image_edit"
                    if route not in {"python", "svg", "image_edit", "image_model"}:
                        continue
                    repairs.append({
                        "asset_id": asset_id,
                        "route": route,
                        "action": check.get("repair_action") or check.get("detail") or "review asset",
                        "source_check": check.get("check_id", "unknown"),
                        "status": "pending",
                    })
        validation = reports[-1] if reports else {}
        artifact = {
            "schema_version": "1.0",
            "artifact_type": "repair_plan",
            "run_id": str(invocation.context["run_id"]),
            "plan_ref": {
                "artifact": "plans/figure_plan.json",
                "content_hash": hash_json(plan),
            },
            "execution_ref": {
                "artifact": "plans/execution_result.json",
                "content_hash": hash_json(execution),
            },
            "validation_ref": {
                "artifact": "validation/final.json",
                "content_hash": hash_json(validation),
            },
            "repairs": repairs,
            "status": "pending" if repairs else "unresolved",
        }
        return {"kind": "repair_plan", "artifact": artifact}


class ProviderPhaseWorker:
    """Model-backed worker that uses one fresh Provider call per invocation."""

    def __init__(self, provider_client: Any,
                 fallback: StructuredPhaseWorker | None = None) -> None:
        self.provider_client = provider_client
        self.fallback = fallback or StructuredPhaseWorker()

    def run(self, invocation: Any) -> Mapping[str, Any]:
        candidate = dict(self.fallback.run(invocation))
        output_schema_name = None
        output_schema = None
        if invocation.phase == "planning":
            output_schema_name = "planning_advice"
            output_schema = json.loads(
                schema_path("planning-advice.schema.json").read_text(
                    encoding="utf-8",
                )
            )
            style_schema = json.loads(
                schema_path("style-bible.schema.json").read_text(
                    encoding="utf-8",
                )
            )
            style_schema.pop("$schema", None)
            style_schema.pop("$id", None)
            output_schema["properties"]["style_bible"]["oneOf"][1] = (
                style_schema
            )
        return self.provider_client.run_phase_worker(
            phase=invocation.phase,
            prompt=invocation.prompt,
            context=dict(invocation.context),
            allowed_tools=list(invocation.allowed_tools),
            fallback_artifact=candidate,
            output_schema_name=output_schema_name,
            output_schema=output_schema,
        )
