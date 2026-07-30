"""Local VLM verification of suspected layout issues (plan section 14).

Only a curated set of issue types are sent to the vision model, and only the
enlarged evidence crop is uploaded. The model's verdict *enriches* the
deterministic check but never downgrades a geometry-confirmed error to a pass.
"""

from __future__ import annotations

from typing import Any

REVIEWABLE_ISSUES = frozenset({
    "text_text_overlap",
    "panel_label_collision",
    "colorbar_collision",
    "unexpected_ai_text",
    "background_residue",
    "legend_obstruction",
})


class VLMVerifier:
    def __init__(self, ark_client: Any, config: dict[str, Any] | None = None) -> None:
        self.ark = ark_client
        config = config or {}
        mm = config.get("multimodal", {})
        if not isinstance(mm, dict):
            mm = {}
        self.enabled = bool(mm.get("enabled", True))
        self.mode = mm.get("mode", "suspicious_regions")
        self.max_regions = int(mm.get("max_regions", 12))
        self.min_confidence = float(mm.get("minimum_issue_confidence", 0.50))

    def review(self, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich failing reviewable checks with a VLM verdict (in place)."""
        if self.ark is None or not self.enabled:
            return checks

        candidates = [
            c for c in checks
            if c.get("status") == "fail"
            and c.get("check_id") in REVIEWABLE_ISSUES
            and c.get("evidence_path")
        ]
        for c in candidates[: self.max_regions]:
            self._review_one(c)
        return checks

    def _review_one(self, check: dict[str, Any]) -> None:
        context = {
            "element_ids": check.get("element_ids", []),
            "bbox": check.get("bbox"),
            "method": check.get("method"),
            "detail": check.get("detail"),
        }
        try:
            verdict = self.ark.verify_local_region(
                check["evidence_path"], check["check_id"], context)
        except Exception as e:  # noqa: BLE001
            # VLM failure: keep the deterministic result, record the skip.
            check["vlm_status"] = "error"
            check["vlm_detail"] = f"verification failed: {e}"
            return

        if not verdict:
            # An empty verdict must not be treated as an implicit pass.
            check["vlm_status"] = "empty"
            return

        check["vlm_confirmed"] = bool(verdict.get("confirmed"))
        check["vlm_confidence"] = verdict.get("confidence")
        if verdict.get("detail"):
            check["vlm_detail"] = verdict["detail"]
        if verdict.get("repair_action"):
            check["repair_action"] = verdict["repair_action"]
        elif verdict.get("move_element_id") and verdict.get("minimum_shift_px"):
            check["repair_action"] = (
                f"move {verdict['move_element_id']} {verdict.get('direction', '')} "
                f"by >= {verdict['minimum_shift_px']} px"
            )

        # Merge policy (plan section 14.4): geometry-confirmed errors are never
        # downgraded to pass by the VLM.
        if check.get("method") == "geometry":
            return
        # For non-geometry (e.g. OCR) suspects, the VLM may reject the issue.
        if not check["vlm_confirmed"] and check.get("vlm_confidence", 0) >= self.min_confidence:
            check["status"] = "pass"
            check["detail"] = (check.get("detail", "") +
                               f" [VLM rejected: {verdict.get('detail', '')}]").strip()


__all__ = ["VLMVerifier", "REVIEWABLE_ISSUES"]
