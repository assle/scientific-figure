"""Exact source-aware checks for authoritative labels and formulas."""

from __future__ import annotations

from typing import Any

from figure_tools.validation.models import LayoutManifest
from figure_tools.validation.summary import make_check


def formal_text_checks(
    figure_plan: dict[str, Any],
    manifest: LayoutManifest | None,
) -> list[dict[str, Any]]:
    expected = {
        str(item["element_id"]): str(item["content"])
        for item in figure_plan.get("text_elements", [])
        if item.get("element_id") and item.get("content") is not None
    }
    formulas = {
        str(item["element_id"]): str(item.get("latex") or item["content"])
        for item in figure_plan.get("text_elements", [])
        if item.get("kind") == "equation" and item.get("element_id")
    }
    if manifest is None:
        return [make_check(
            "formal_text_exact_match",
            "final",
            "error",
            "fail" if expected else "pass",
            "layout evidence is unavailable for authoritative text comparison",
            element_ids=sorted(expected),
            method="layout_manifest_text",
        )]
    observed = {
        element.element_id: element.text
        for element in manifest.elements
        if element.text is not None
    }
    mismatched = sorted(
        element_id for element_id, content in expected.items()
        if observed.get(element_id) != content
    )
    formula_mismatches = sorted(
        element_id for element_id, content in formulas.items()
        if observed.get(element_id) != content
    )
    return [
        make_check(
            "formal_text_exact_match",
            "final",
            "error",
            "fail" if mismatched else "pass",
            (
                "mismatched or missing formal text: " + ", ".join(mismatched)
                if mismatched else "all authoritative labels match exactly"
            ),
            element_ids=mismatched,
            method="layout_manifest_text",
        ),
        make_check(
            "formula_exact_match",
            "final",
            "error",
            "fail" if formula_mismatches else "pass",
            (
                "mismatched or missing formulas: " + ", ".join(formula_mismatches)
                if formula_mismatches else "all authoritative formulas match exactly"
            ),
            element_ids=formula_mismatches,
            method="layout_manifest_text",
        ),
    ]


__all__ = ["formal_text_checks"]
