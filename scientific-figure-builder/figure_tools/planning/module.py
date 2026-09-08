"""Deep Figure Planning Module for deterministic plan construction."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator

from figure_tools._resources import schema_path
from figure_tools.planning.planner import create_figure_plan, resolve_figure_canvas
from figure_tools.planning.advice import default_planning_advice
from figure_tools.provenance import hash_json
from figure_tools.style_spec import StyleResolutionError, resolve_style_bible, style_digest


class PlanningAdviceError(ValueError):
    """Planning Advice is invalid or conflicts with deterministic plan facts."""


class FigurePlanningModule:
    """Build a canonical Figure plan from a Figure brief and narrow advice."""

    def __init__(self, default_canvas: Mapping[str, Any] | None = None) -> None:
        self.default_canvas = dict(default_canvas or {}) or None

    def build_plan(
        self,
        brief: Mapping[str, Any],
        advice: Mapping[str, Any],
        *,
        revision: int,
        base_dir: str = ".",
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        self._validate_advice(advice)
        if brief.get("status") != "ready":
            raise PlanningAdviceError("Planning requires a ready Figure brief")

        request = copy.deepcopy(dict(brief["request"]))
        request.update(brief.get("delivery") or {})
        request["language"] = brief.get("language")
        request["style"] = brief.get("style")
        request["canvas"] = resolve_figure_canvas(
            request, default_canvas=self.default_canvas,
        )
        request["panels"] = self._normalize_panels(
            request.get("panels", []), request["canvas"],
        )
        request["brief_ref"] = {
            "artifact": "plans/figure_brief.json",
            "content_hash": hash_json(brief),
        }
        try:
            style_bible, style_source = resolve_style_bible(
                request.get("style"),
                advice_style_bible=advice.get("style_bible"),
                base_dir=base_dir,
            )
        except StyleResolutionError as exc:
            raise PlanningAdviceError(f"style resolution failed: {exc}") from exc
        plan = create_figure_plan(
            request, style_bible_ref="style_bible.json",
        )
        plan["revision"] = int(revision)
        plan["plan_id"] = f"{plan['figure_id']}-plan-v{revision}"
        composition = copy.deepcopy(dict(advice["composition"]))
        if (
            any(unit["method"] == "image_model" for unit in plan["generation_units"])
            and not composition.get("regions")
        ):
            composition = default_planning_advice(brief)["composition"]
        if not composition.get("forbidden_patterns"):
            composition["forbidden_patterns"] = list(
                style_bible.get("forbidden_elements", [])
            )
        self._validate_composition(request, composition)
        plan["composition"] = composition
        plan["style_source"] = style_source
        plan["style_summary"] = style_digest(style_bible)
        self._apply_asset_hints(plan, advice.get("asset_hints", []))
        return plan, request, style_bible

    @staticmethod
    def _validate_advice(advice: Mapping[str, Any]) -> None:
        contract = json.loads(
            schema_path("planning-advice.schema.json").read_text(encoding="utf-8")
        )
        errors = sorted(
            Draft202012Validator(contract).iter_errors(dict(advice)),
            key=lambda error: list(error.path),
        )
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise PlanningAdviceError(f"invalid Planning Advice: {detail}")

    @staticmethod
    def _apply_asset_hints(plan: dict[str, Any], raw_hints: Any) -> None:
        assets = {str(asset["asset_id"]): asset for asset in plan["assets"]}
        seen: set[str] = set()
        for hint in raw_hints:
            asset_id = str(hint["asset_id"])
            if asset_id in seen:
                raise PlanningAdviceError(
                    f"invalid Planning Advice: duplicate asset hint {asset_id!r}"
                )
            if asset_id not in assets:
                raise PlanningAdviceError(
                    f"invalid Planning Advice: unknown asset hint {asset_id!r}"
                )
            seen.add(asset_id)
            assets[asset_id]["bbox"] = list(hint["bbox"])

    @staticmethod
    def _normalize_panels(
        raw_panels: Any,
        canvas: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        panels = [copy.deepcopy(dict(panel)) for panel in raw_panels]
        single = len(panels) == 1
        for panel in panels:
            panel_id = str(panel.get("panel_id") or "")
            panel.setdefault("elements", [])
            if "bbox" not in panel:
                if not single:
                    raise PlanningAdviceError(
                        f"panel {panel_id!r} is missing bbox; multiple panels need explicit layout"
                    )
                panel["bbox"] = [0, 0, 1, 1]
            if "physical_size" not in panel:
                bbox = list(panel["bbox"])
                if len(bbox) != 4:
                    raise PlanningAdviceError(
                        f"panel {panel_id!r} has an invalid bbox"
                    )
                panel["physical_size"] = [
                    float(canvas["width"]) * float(bbox[2]),
                    float(canvas["height"]) * float(bbox[3]),
                ]
        return panels

    @staticmethod
    def _validate_composition(
        request: Mapping[str, Any], composition: Mapping[str, Any],
    ) -> None:
        known = {
            str(element["element_id"])
            for panel in request.get("panels", [])
            for element in panel.get("elements", [])
        }
        known.update(
            str(label["element_id"]) for label in request.get("labels", [])
        )
        region_ids: set[str] = set()
        represented: set[str] = set()
        for region in composition.get("regions", []):
            region_id = str(region["region_id"])
            if region_id in region_ids:
                raise PlanningAdviceError(
                    f"invalid Planning Advice: duplicate composition region {region_id!r}"
                )
            region_ids.add(region_id)
            nodes = {str(node_id) for node_id in region.get("node_ids", [])}
            unknown = sorted(nodes - known)
            if unknown:
                raise PlanningAdviceError(
                    "invalid Planning Advice: composition references unknown nodes "
                    + ", ".join(unknown)
                )
            duplicate = sorted(nodes & represented)
            if duplicate:
                raise PlanningAdviceError(
                    "invalid Planning Advice: composition repeats nodes "
                    + ", ".join(duplicate)
                )
            represented.update(nodes)


__all__ = ["FigurePlanningModule", "PlanningAdviceError"]
