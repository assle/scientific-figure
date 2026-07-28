"""Step orchestrator with resume and incremental invalidation (plan section 15).

Phase 3 exit criteria:
- An interrupted deterministic run resumes without repeating completed work.
- Local edits invalidate only affected downstream artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from figure_tools.state import RunState


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
