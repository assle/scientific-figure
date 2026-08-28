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
        "Do not generate assets or change the brief."
    ),
    "review_and_repair": (
        "Review the execution result against the approved Figure brief and plan. "
        "Return validation enrichment or a targeted Repair plan only."
    ),
}


def prompt_for(phase: str) -> str:
    try:
        return PHASE_PROMPTS[phase]
    except KeyError as exc:
        raise ValueError(f"no phase prompt for {phase!r}") from exc
