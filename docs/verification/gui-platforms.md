# GUI and delivery verification

This document is the current verification record for the native Configuration
app and its private runtime delivery. It is evidence, not a changelog.

## Automated evidence

Run from `scientific-figure-builder/`:

```bash
uv run --extra gui pytest -q
uv build --wheel
```

The suite covers offscreen Qt creation, Provider CRUD, FakeSecretStore
credential replacement/deletion, background connection testing with Fake
Transport, OpenAI/Anthropic/DashScope Provider configuration, launcher conflict
protection, global/project install scope,
Keyring-cleanup failure retention, MCP tool verification, CLI help, and wheel
resource import. Tests do not access a real model endpoint or system Keyring.

The recorded local run on 2026-09-05 after adding the DashScope Native image
dialect, budgeted dynamic structured-output expansion, installed-wheel resource
verification, and edge-connected background removal completed with **572
passed, 3 skipped** (`SCIENTIFIC_FIGURE_CONFIG=/dev/null .venv/bin/pytest -q`).
The skipped acceptance tests require explicitly configured real Providers and
the optional PowerPoint desktop E2E test; neither is part of the no-network CI
gate.
`uv build --wheel` also completed successfully and the wheel contained
`figure_tools/resources/icon.svg`, the QML
component bundle, and the delivery cleanup modules.
The opt-in Microsoft PowerPoint desktop E2E test also passed on macOS after
PowerPoint was activated, including SVG insertion, conversion, and ungrouping.
The repository-wide Pyright check completed with **0 errors, 0 warnings, and 0
information diagnostics** (`uvx pyright --pythonpath .venv/bin/python figure_tools install`).

## Platform matrix

| Platform | Covered behavior | Limitation |
| --- | --- | --- |
| macOS | Offscreen GUI, Keyring seam, global launcher, atomic config save, wheel resources | A human must run one signed/desktop Keychain smoke test after installation |
| Windows | Path-independent atomic write, launcher `.cmd` rendering, Keyring seam, Chinese UI strings | Credential Manager backend and a visible desktop session require a Windows host |
| Linux | Fake secure-backend success/failure, environment fallback, no-DISPLAY MCP import path | Secret Service availability depends on the desktop session; headless use should use `key_env` |

The installer always verifies the two-tool lifecycle MCP response, CLI help, marked
launcher (global scope), and packaged GUI resource import without opening a
window. The documented host limitations are the only checks that require a
real platform session.
