"""Run state, budget/retry accounting, cache, and run-directory versioning.

Plan sections 7, 12, and 15 (Phase 3).
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any


class BudgetExceeded(Exception):
    """Raised when a paid call or quality retry would exceed the configured budget."""


class RunState:
    def __init__(
        self,
        run_id: str,
        parent_run_id: str | None = None,
        budget: dict[str, int] | None = None,
    ) -> None:
        self.run_id = run_id
        self.parent_run_id = parent_run_id
        self.current_step = ""
        self._steps: dict[str, dict] = {}
        self._calls: dict[str, int] = {}
        self.budget: dict[str, int] = dict(budget or {})
        self._retries: dict[str, dict[str, int]] = {}
        self.cache_hits = 0
        self._approvals: dict[str, str] = {}
        self.resume: dict[str, Any] = {"from_step": "", "invalidate_downstream": False}

    # --- steps -----------------------------------------------------------
    def mark_step(self, step: str, status: str, output_hashes: dict | None = None) -> None:
        self.current_step = step
        self._steps[step] = {
            "status": status,
            "output_hashes": dict(output_hashes or {}),
        }

    def is_completed(self, step: str) -> bool:
        return self._steps.get(step, {}).get("status") == "completed"

    def step_status(self, step: str) -> str:
        return self._steps.get(step, {}).get("status", "pending")

    def output_hashes(self, step: str) -> dict:
        return self._steps.get(step, {}).get("output_hashes", {})

    def clear_step(self, step: str) -> None:
        self._steps.pop(step, None)

    # --- calls / budget --------------------------------------------------
    def record_call(self, role: str, count: int = 1) -> None:
        self._calls[role] = self._calls.get(role, 0) + count
        if role in self.budget and self._calls[role] > self.budget[role]:
            raise BudgetExceeded(
                f"budget for {role!r} exceeded: {self._calls[role]} > {self.budget[role]}"
            )

    def calls_used(self, role: str) -> int:
        return self._calls.get(role, 0)

    def calls_remaining(self, role: str) -> int:
        if role not in self.budget:
            return 0
        return max(0, self.budget[role] - self._calls.get(role, 0))

    # --- retries ---------------------------------------------------------
    def record_retry(self, role: str, kind: str) -> None:
        if kind not in ("transient", "quality"):
            raise ValueError(f"unknown retry kind: {kind}")
        bucket = self._retries.setdefault(role, {"transient": 0, "quality": 0})
        bucket[kind] += 1
        if kind == "quality" and bucket["quality"] > 2:
            raise BudgetExceeded(
                f"quality retries for {role!r} exceeded 2: {bucket['quality']}"
            )

    def retries(self, role: str, kind: str) -> int:
        return self._retries.get(role, {"transient": 0, "quality": 0}).get(kind, 0)

    # --- approvals -------------------------------------------------------
    def request_approval(self, checkpoint: str, status: str) -> None:
        self._approvals[checkpoint] = status

    # --- resume ----------------------------------------------------------
    def set_resume(self, from_step: str, invalidate_downstream: bool = False) -> None:
        self.resume = {"from_step": from_step, "invalidate_downstream": invalidate_downstream}

    # --- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        steps = [
            {"step": name, "status": s["status"], "output_hashes": s["output_hashes"]}
            for name, s in self._steps.items()
        ]
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "current_step": self.current_step or self.resume.get("from_step", "") or "init",
            "steps": steps,
            "calls": {"counts": self._calls, "budget": self.budget},
            "retries": {
                "transient": {r: v["transient"] for r, v in self._retries.items()},
                "quality": {r: v["quality"] for r, v in self._retries.items()},
            },
            "cache_hits": self.cache_hits,
            "approval_checkpoints": [
                {"checkpoint": k, "status": v} for k, v in self._approvals.items()
            ],
            "resume": {
                "from_step": self.resume.get("from_step", "") or "init",
                "invalidate_downstream": bool(self.resume.get("invalidate_downstream", False)),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        state = cls(
            run_id=data["run_id"],
            parent_run_id=data.get("parent_run_id"),
            budget=dict(data.get("calls", {}).get("budget", {})),
        )
        state.current_step = data.get("current_step", "")
        for s in data.get("steps", []):
            state._steps[s["step"]] = {
                "status": s["status"],
                "output_hashes": dict(s.get("output_hashes", {})),
            }
        state._calls = dict(data.get("calls", {}).get("counts", {}))
        retries = data.get("retries", {})
        for kind in ("transient", "quality"):
            for role, n in retries.get(kind, {}).items():
                state._retries.setdefault(role, {"transient": 0, "quality": 0})[kind] = n
        state.cache_hits = data.get("cache_hits", 0)
        for a in data.get("approval_checkpoints", []):
            state._approvals[a["checkpoint"]] = a["status"]
        state.resume = {
            "from_step": data.get("resume", {}).get("from_step", ""),
            "invalidate_downstream": data.get("resume", {}).get("invalidate_downstream", False),
        }
        return state

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "RunState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


class Cache:
    """Content-addressed cache for paid model outputs (plan section 12)."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(
        model_id: str,
        prompt_hash: str,
        parameters: dict,
        reference_hashes: list[str],
    ) -> str:
        payload = json.dumps(
            {
                "model": model_id,
                "prompt": prompt_hash,
                "parameters": parameters,
                "references": sorted(reference_hashes),
            },
            sort_keys=True,
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.cache_dir / key.replace(":", "_")

    def get(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.exists() else None

    def put(self, key: str, src_path: str | Path) -> Path:
        dst = self._path(key)
        shutil.copyfile(src_path, dst)
        return dst


_RUN_SUBDIRS = (
    "inputs", "plans", "prompts", "assets", "plots", "vectors",
    "validation", "exports",
)


class RunDirectory:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.runs_dir = self.base_dir / "runs"

    def create(self, figure_id: str) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = date.today().isoformat()
        slug = figure_id.replace("/", "-")
        candidate = self.runs_dir / f"{stamp}_{slug}"
        counter = 1
        while candidate.exists():
            candidate = self.runs_dir / f"{stamp}_{slug}-{counter}"
            counter += 1
        self.ensure_structure(candidate)
        return candidate

    @staticmethod
    def ensure_structure(run_dir: str | Path) -> Path:
        run_dir = Path(run_dir)
        for sub in _RUN_SUBDIRS:
            (run_dir / sub).mkdir(parents=True, exist_ok=True)
        return run_dir
