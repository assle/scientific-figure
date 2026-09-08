"""Durable local orchestration for Lifecycle advances that outlive callers."""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from figure_tools.run_store import RunStore


_ACTIVE_LOCK = threading.RLock()
_ACTIVE: dict[str, tuple[str, threading.Thread]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


class LocalPhaseOperationManager:
    """Start or observe one idempotent local Lifecycle operation per run."""

    def start_or_observe(
        self,
        run_dir: str | Path,
        operation: Callable[[], Mapping[str, Any]],
        *,
        wait_timeout: float,
        phase_hint: str,
        context: Any = None,
    ) -> dict[str, Any]:
        store = RunStore(run_dir)
        store.ensure_structure()
        key = str(Path(run_dir).resolve())
        with _ACTIVE_LOCK:
            existing = store.load_optional_json(
                "plans/phase_operation.json", schema="phase-operation.schema.json",
            )
            observed = self._observe_existing(store, key, existing)
            if observed is not None:
                return observed
            operation_id = uuid.uuid4().hex
            self._claim(store, operation_id)
            timestamp = _now()
            state = {
                "schema_version": "1.0",
                "operation_id": operation_id,
                "phase": phase_hint,
                "status": "running",
                "owner_pid": os.getpid(),
                "created_at": timestamp,
                "updated_at": timestamp,
                "provider_invocation_id": None,
                "result": None,
                "error": None,
            }
            store.commit_json(
                "plans/phase_operation.json", state,
                schema="phase-operation.schema.json",
            )
            thread = threading.Thread(
                target=self._run,
                args=(store, key, operation_id, operation, context),
                daemon=True,
                name=f"scientific-figure-{operation_id[:8]}",
            )
            _ACTIVE[key] = (operation_id, thread)
            thread.start()
        thread.join(max(0.0, float(wait_timeout)))
        with _ACTIVE_LOCK:
            current = store.load_json(
                "plans/phase_operation.json", schema="phase-operation.schema.json",
            )
            if current.get("status") == "failed":
                raise RuntimeError(str(current.get("error") or "Lifecycle operation failed"))
            observed = self._observe_existing(store, key, current)
            if observed is not None:
                return observed
            return self._in_progress(store, current)

    def _observe_existing(
        self,
        store: RunStore,
        key: str,
        existing: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if existing is None or existing.get("status") == "consumed":
            return None
        existing = self._with_runtime_evidence(store, existing)
        status = str(existing["status"])
        if status == "completed":
            result = existing.get("result")
            if not isinstance(result, Mapping):
                return self._failed_result(store, existing, "completed operation has no result")
            consumed = {**existing, "status": "consumed", "updated_at": _now()}
            store.commit_json(
                "plans/phase_operation.json", consumed,
                schema="phase-operation.schema.json",
            )
            return dict(result)
        if status == "failed":
            return self._failed_result(store, existing, str(existing.get("error") or "operation failed"))
        if status == "remote_outcome_unknown":
            return self._unknown_result(store, existing)
        active = _ACTIVE.get(key)
        if active is not None and active[0] == existing["operation_id"] and active[1].is_alive():
            return self._in_progress(store, existing)
        if _process_exists(int(existing["owner_pid"])):
            return self._in_progress(store, existing)
        unknown = {
            **existing,
            "status": "remote_outcome_unknown",
            "updated_at": _now(),
            "error": "local operation owner disappeared; remote outcome unknown",
        }
        store.commit_json(
            "plans/phase_operation.json", unknown,
            schema="phase-operation.schema.json",
        )
        return self._unknown_result(store, unknown)

    @staticmethod
    def _claim(store: RunStore, operation_id: str) -> None:
        lock_path = store.path("plans/.phase-operation.lock")
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("another Lifecycle operation already owns this run") from exc
        try:
            os.write(descriptor, operation_id.encode("ascii"))
        finally:
            os.close(descriptor)

    @staticmethod
    def _run(
        store: RunStore,
        key: str,
        operation_id: str,
        operation: Callable[[], Mapping[str, Any]],
        context: Any,
    ) -> None:
        try:
            value = context.run(operation) if context is not None else operation()
            result = dict(value)
            current = store.load_json("plans/phase_operation.json")
            completed = {
                **current,
                "phase": str(result.get("phase") or current["phase"]),
                "status": "completed",
                "updated_at": _now(),
                "result": result,
                "error": None,
            }
            store.commit_json(
                "plans/phase_operation.json", completed,
                schema="phase-operation.schema.json",
            )
        except BaseException as exc:  # error is already sanitized by the MCP Adapter
            current = store.load_optional_json("plans/phase_operation.json") or {
                "schema_version": "1.0", "operation_id": operation_id,
                "phase": "intake", "owner_pid": os.getpid(),
                "created_at": _now(), "result": None,
                "provider_invocation_id": None,
            }
            failed = {
                **current,
                "status": "failed",
                "updated_at": _now(),
                "result": None,
                "error": str(exc),
            }
            store.commit_json(
                "plans/phase_operation.json", failed,
                schema="phase-operation.schema.json",
            )
        finally:
            store.path("plans/.phase-operation.lock").unlink(missing_ok=True)
            with _ACTIVE_LOCK:
                active = _ACTIVE.get(key)
                if active is not None and active[0] == operation_id:
                    _ACTIVE.pop(key, None)

    @staticmethod
    def _in_progress(store: RunStore, operation: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "phase": str(operation["phase"]),
            "status": "in_progress",
            "next_action": "resume",
            "artifacts": {"operation": store.reference("plans/phase_operation.json")},
            "operation_id": str(operation["operation_id"]),
            "operation_status": "running",
        }

    @staticmethod
    def _with_runtime_evidence(
        store: RunStore, operation: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_state = store.load_optional_json("run_state.json") or {}
        statuses = run_state.get("provider_status") or {}
        provider_status = statuses.get("phase_reasoning") or {}
        invocation_id = provider_status.get("invocation_id")
        phase = run_state.get("current_phase") or operation.get("phase")
        if (
            invocation_id == operation.get("provider_invocation_id")
            and phase == operation.get("phase")
        ):
            return dict(operation)
        updated = {
            **operation,
            "phase": str(phase),
            "provider_invocation_id": (
                str(invocation_id) if invocation_id is not None else None
            ),
            "updated_at": _now(),
        }
        store.commit_json(
            "plans/phase_operation.json", updated,
            schema="phase-operation.schema.json",
        )
        return updated

    @staticmethod
    def _failed_result(
        store: RunStore, operation: Mapping[str, Any], error: str,
    ) -> dict[str, Any]:
        return {
            "phase": str(operation["phase"]),
            "status": "paused",
            "next_action": None,
            "artifacts": {"operation": store.reference("plans/phase_operation.json")},
            "operation_id": str(operation["operation_id"]),
            "operation_status": "failed",
            "error": error,
            "recovery": "Inspect the saved operation before explicitly starting new work.",
        }

    @staticmethod
    def _unknown_result(store: RunStore, operation: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "phase": str(operation["phase"]),
            "status": "paused",
            "next_action": None,
            "artifacts": {"operation": store.reference("plans/phase_operation.json")},
            "operation_id": str(operation["operation_id"]),
            "operation_status": "remote_outcome_unknown",
            "error": str(operation.get("error") or "remote outcome unknown"),
            "recovery": "Do not resubmit automatically; inspect Provider and Run State evidence first.",
        }


__all__ = ["LocalPhaseOperationManager"]
