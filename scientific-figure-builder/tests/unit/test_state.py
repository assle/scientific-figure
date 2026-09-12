"""Run state, budget, retry, cache, and approval tests (plan sections 7 and 12)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from figure_tools.state import BudgetExceeded, Cache, RunDirectory, RunState

DEFAULT_BUDGET = {
    "reference_analysis": 1,
    "generation": 3,
    "edits": 2,
    "validations": 5,
    "final_validation": 1,
}


def _new_state() -> RunState:
    return RunState(run_id="2026-07-28_figure-01", budget=DEFAULT_BUDGET)


def test_run_state_conforms_to_schema(tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator

    from figure_tools._resources import schema_path

    state = _new_state()
    state.mark_step("create_plan", "completed", {"figure_plan.json": "sha256:p"})
    state.mark_step("render_plots", "running")
    state.record_call("reference_analysis")
    state.record_retry("generation", "quality")
    state.request_approval("plan_approval", "approved")
    state.set_resume("render_plots")
    data = state.to_dict()
    schema = json.loads(schema_path("run-state.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(data))
    assert not errors, [e.message for e in errors]


def test_mark_step_and_is_completed() -> None:
    state = _new_state()
    assert not state.is_completed("create_plan")
    state.mark_step("create_plan", "completed", {"figure_plan.json": "sha256:x"})
    assert state.is_completed("create_plan")
    assert state.output_hashes("create_plan") == {"figure_plan.json": "sha256:x"}


def test_record_call_and_budget_enforcement() -> None:
    state = _new_state()
    state.record_call("reference_analysis")
    assert state.calls_used("reference_analysis") == 1
    assert state.calls_remaining("reference_analysis") == 0
    with pytest.raises(BudgetExceeded):
        state.record_call("reference_analysis")  # over budget
    assert state.calls_used("reference_analysis") == 1


def test_transient_and_quality_retries_separate() -> None:
    state = _new_state()
    state.record_retry("generation", "transient")
    state.record_retry("generation", "transient")
    state.record_retry("generation", "quality")
    assert state.retries("generation", "transient") == 2
    assert state.retries("generation", "quality") == 1
    # Quality retry limit enforced (max 2 per asset per plan section 12).
    state.record_retry("generation", "quality")
    with pytest.raises(BudgetExceeded):
        state.record_retry("generation", "quality")


def test_save_load_round_trip(tmp_path: Path) -> None:
    state = _new_state()
    state.mark_step("create_plan", "completed", {"figure_plan.json": "sha256:p"})
    state.record_call("reference_analysis")
    state.request_approval("plan_approval", "approved")
    path = tmp_path / "run_state.json"
    state.save(path)
    loaded = RunState.load(path)
    assert loaded.is_completed("create_plan")
    assert loaded.calls_used("reference_analysis") == 1
    assert loaded.to_dict()["run_id"] == "2026-07-28_figure-01"


def test_run_directory_versioning(tmp_path: Path) -> None:
    rd = RunDirectory(base_dir=tmp_path)
    run1 = rd.create("figure-01")
    run2 = rd.create("figure-01")
    assert run1 != run2
    assert run1.name.startswith("2026-")
    for sub in ("inputs", "plans", "assets", "plots", "vectors", "validation",
                "exports", "prompts"):
        assert (run1 / sub).is_dir()


def test_cache_key_deterministic_and_hit(tmp_path: Path) -> None:
    cache = Cache(cache_dir=tmp_path / "cache")
    key = Cache.make_key("model-x", "sha256:prompt", {"size": "1024"}, ["sha256:ref"])
    assert key == Cache.make_key("model-x", "sha256:prompt", {"size": "1024"}, ["sha256:ref"])
    assert cache.get(key) is None
    src = tmp_path / "asset.png"
    src.write_bytes(b"fake-png")
    cache.put(key, src)
    hit = cache.get(key)
    assert hit is not None and hit.exists()
    assert hit.read_bytes() == b"fake-png"


def test_cache_distinct_keys_for_different_inputs(tmp_path: Path) -> None:
    k1 = Cache.make_key("m", "p1", {}, [])
    k2 = Cache.make_key("m", "p2", {}, [])
    assert k1 != k2


def test_cache_readers_never_observe_a_partial_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader sharing the cache with a writer must not see a half-written value.

    Two concurrent mock assets can request the same key, so one thread can be
    reading while another is storing. Callers parse what they read back, and a
    zero-byte read is not a cache miss.
    """
    cache = Cache(cache_dir=tmp_path / "cache")
    key = "sha256:" + "ab" * 32
    destination = cache._path(key)
    real_write_bytes = Path.write_bytes

    def truncate_then_delay(path: Path, data: bytes) -> int:
        if path.parent != cache.cache_dir:
            return real_write_bytes(path, data)
        # Emulate the observable half-state: the file exists at zero length
        # while its content is still being produced.
        with path.open("wb"):
            pass
        time.sleep(0.2)
        return real_write_bytes(path, data)

    observed: set[bytes | None] = set()
    stop = threading.Event()

    def read_until_published() -> None:
        while not stop.is_set():
            observed.add(cache.get_bytes(key))

    monkeypatch.setattr(Path, "write_bytes", truncate_then_delay)
    reader = threading.Thread(target=read_until_published)
    reader.start()
    try:
        cache.put_bytes(key, b"complete")
    finally:
        stop.set()
        reader.join()

    assert destination.read_bytes() == b"complete"
    assert observed <= {None, b"complete"}, observed
    assert sorted(cache.cache_dir.iterdir()) == [destination]


def test_cache_write_retries_a_transient_windows_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows rejects the publishing move while another handle reads the file."""
    cache = Cache(cache_dir=tmp_path / "cache")
    key = "sha256:" + "cd" * 32
    destination = cache._path(key)
    real_replace = os.replace
    attempts: list[str] = []

    def reject_once(source, target) -> None:
        attempts.append(str(source))
        if len(attempts) == 1:
            raise PermissionError("destination is open for reading")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", reject_once)
    cache.put_bytes(key, b"complete")

    assert len(attempts) == 2
    assert cache.get_bytes(key) == b"complete"
    assert sorted(cache.cache_dir.iterdir()) == [destination]
