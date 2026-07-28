"""Resume and incremental invalidation tests (plan section 15, Phase 3 exit criteria).

- An interrupted deterministic run resumes without repeating completed work.
- Local edits invalidate only affected downstream artifacts.
"""

from __future__ import annotations

from pathlib import Path

from figure_tools.orchestrator import Step, StepRunner
from figure_tools.state import RunState

BUDGET = {"reference_analysis": 1, "generation": 3, "validations": 5,
          "edits": 2, "final_validation": 1}


def _state() -> RunState:
    return RunState(run_id="run-1", budget=BUDGET)


def test_resume_skips_completed_steps(tmp_path: Path) -> None:
    state = _state()
    # Simulate prior progress: plan and plots already completed.
    state.mark_step("create_plan", "completed", {"plan.json": "sha256:p"})
    state.mark_step("render_plots", "completed", {"plot.png": "sha256:plot"})
    state.mark_step("assemble", "pending")
    state.set_resume("assemble")

    executed: list[str] = []

    steps = [
        Step("create_plan", lambda ctx: executed.append("create_plan") or {"plan.json": "h"}),
        Step("render_plots", lambda ctx: executed.append("render_plots") or {"plot.png": "h"}),
        Step("assemble", lambda ctx: executed.append("assemble") or {"figure.png": "h"}),
    ]
    runner = StepRunner(state, run_dir=tmp_path)
    runner.run(steps)

    assert executed == ["assemble"], f"should only run assemble, got {executed}"


def test_full_run_executes_all_when_nothing_completed(tmp_path: Path) -> None:
    state = _state()
    executed: list[str] = []
    steps = [
        Step("create_plan", lambda ctx: executed.append("create_plan") or {"plan.json": "h"}),
        Step("render_plots", lambda ctx: executed.append("render_plots") or {"plot.png": "h"}),
        Step("assemble", lambda ctx: executed.append("assemble") or {"figure.png": "h"}),
    ]
    StepRunner(state, run_dir=tmp_path).run(steps)
    assert executed == ["create_plan", "render_plots", "assemble"]


def test_invalidation_only_affects_downstream(tmp_path: Path) -> None:
    state = _state()
    # All steps previously completed.
    state.mark_step("load_data", "completed", {"data.csv": "sha256:d"})
    state.mark_step("render_plots", "completed", {"plot.png": "sha256:p"})
    state.mark_step("assemble", "completed", {"figure.png": "sha256:f"})
    state.mark_step("write_report", "completed", {"report.md": "sha256:r"})  # independent-ish

    executed: list[str] = []

    def make(name, out):
        def fn(ctx):
            executed.append(name)
            return out
        return fn

    steps = [
        Step("load_data", make("load_data", {"data.csv": "h"})),
        Step("render_plots", make("render_plots", {"plot.png": "h"}), depends_on=["load_data"]),
        Step("assemble", make("assemble", {"figure.png": "h"}), depends_on=["render_plots"]),
        Step("write_report", make("write_report", {"report.md": "h"}), depends_on=["assemble"]),
    ]

    runner = StepRunner(state, run_dir=tmp_path)
    # A local edit to source data invalidates load_data and its downstream.
    runner.invalidate_from("load_data", steps)
    runner.run(steps)

    # write_report depends on assemble (downstream of load_data) so it is also
    # invalidated. Everything downstream of load_data re-runs; nothing upstream
    # exists. So all four re-run.
    assert executed == ["load_data", "render_plots", "assemble", "write_report"]


def test_invalidation_preserves_independent_branch(tmp_path: Path) -> None:
    state = _state()
    state.mark_step("render_plots", "completed", {"plot.png": "sha256:p"})
    state.mark_step("render_inset", "completed", {"inset.png": "sha256:i"})
    state.mark_step("assemble", "completed", {"figure.png": "sha256:f"})

    executed: list[str] = []

    def make(name, out):
        def fn(ctx):
            executed.append(name)
            return out
        return fn

    steps = [
        Step("render_plots", make("render_plots", {"plot.png": "h"})),
        Step("render_inset", make("render_inset", {"inset.png": "h"})),  # independent
        Step("assemble", make("assemble", {"figure.png": "h"}), depends_on=["render_plots"]),
    ]
    runner = StepRunner(state, run_dir=tmp_path)
    # Invalidate only render_plots -> render_inset must stay completed.
    runner.invalidate_from("render_plots", steps)
    runner.run(steps)

    assert "render_inset" not in executed, "independent branch should not be invalidated"
    assert executed == ["render_plots", "assemble"]


def test_runner_persists_state_between_runs(tmp_path: Path) -> None:
    state_path = tmp_path / "run_state.json"
    state = _state()
    state.save(state_path)

    executed: list[str] = []
    steps = [Step("create_plan", lambda ctx: executed.append("create_plan") or {"p": "h"})]
    runner = StepRunner(state, run_dir=tmp_path, state_path=state_path)
    runner.run(steps)
    assert state.is_completed("create_plan")

    # New runner loading persisted state should skip create_plan.
    executed.clear()
    state2 = RunState.load(state_path)
    runner2 = StepRunner(state2, run_dir=tmp_path, state_path=state_path)
    runner2.run(steps)
    assert executed == []
