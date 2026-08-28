---
description: Orchestrate a scientific figure through the lifecycle orchestrator
---
You are invoking the scientific-figure-builder skill. Load its lifecycle router
and use the single `advance_figure_workflow` tool for task runs. The tool owns
phase transitions and returns the next user action.

Interpret the requested subcommand from `$ARGUMENTS` as follows:

- `init` - initialize project configuration (`.scientific-figure/`) with no
  secrets. Provider credentials come from the system credential store or the
  configured environment variable; never write values into configuration.
- `gui` - open the native Chinese global model/provider configuration window;
  it does not start a browser, server, or network connection.
- `plan` - submit the request to the orchestrator and follow its Intake and
  Planning next actions until the Figure plan and wireframe are ready.
- `run` - submit the plan approval or execution action returned by the
  orchestrator and follow its next action through Execution and Review.
- `resume` - submit `resume` with the run directory; reuse completed Phase
  artifacts and paid results.
- `validate` - continue the Review and repair phase and surface its Validation report or
  Repair plan.
- `export` - continue the Export phase, respecting the Export gate and any
  explicit force-export choice and audit reason.

The orchestrator enforces routing, clarification, approval, budget, validation,
privacy, and export rules. Do not write ad-hoc plotting scripts or call
low-level generation/assembly tools directly for a normal lifecycle run.
