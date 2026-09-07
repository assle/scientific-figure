"""Versioned prompts used by the lifecycle Phase workers.

The Calling Agent may route work into a lifecycle phase, but these prompts are
the single source for worker-specific reasoning instructions and provenance.
"""

from __future__ import annotations

PHASE_PROMPT_VERSION = "1.0"

PHASE_PROMPTS = {
    "intake": (
        "Resolve the scientific figure request and required clarifications. "
        "Return only a Figure brief suggestion; do not render or call a Provider."
    ),
    "planning": (
        "Turn the completed Figure brief into a reproducible Figure plan. "
        "Preserve explicit image-generation intent as image_asset. "
        "vector_element.content must be complete SVG source, never prose. "
        "Do not generate assets or change the brief."
    ),
    "review_and_repair": (
        "Review the execution result against the approved Figure brief and plan. "
        "Return one JSON object with kind and artifact. kind must be "
        "validation_report or repair_plan; artifact must satisfy the matching schema. "
        "For repair_plan preserve schema_version, artifact_type, run_id, plan_ref, "
        "execution_ref, validation_ref, repairs, and status from the supplied "
        "fallback artifact. Include repairs even when empty, and use unresolved "
        "when no executable repair is available. Never claim repair success or "
        "downgrade deterministic failures."
    ),
}


def prompt_for(phase: str) -> str:
    try:
        return PHASE_PROMPTS[phase]
    except KeyError as exc:
        raise ValueError(f"no phase prompt for {phase!r}") from exc
