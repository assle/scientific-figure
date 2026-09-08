---
description: Route a request through Scientific Figure Builder
---

Load the `scientific-figure-builder` skill and route `$ARGUMENTS` through it.

Use `initialize_figure_project` for `init`. Use the native global configuration
window for `gui`. For `plan`, `run`, `resume`, `validate`, or `export`, express
the requested lifecycle goal through `advance_figure_workflow` and follow the
Skill's routing contract.
