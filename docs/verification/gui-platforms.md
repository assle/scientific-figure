# GUI and delivery verification

This document records reproducible checks and dated evidence for the native
Configuration app and its private runtime delivery. It is evidence, not a
changelog or a promise that an old count still describes the current tree.

## Automated evidence

Run from `scientific-figure-builder/`:

```bash
uv run --frozen pytest -q
python3 ../scripts/verify_release_candidate.py --build
```

The suite covers offscreen Qt creation, Provider CRUD, FakeSecretStore
credential replacement/deletion, background connection testing with Fake
Transport, OpenAI/Anthropic/DashScope Provider configuration, launcher conflict
protection, global/project install scope,
Keyring-cleanup failure retention, MCP tool verification, CLI help, and wheel
resource import. Tests do not access a real model endpoint or system Keyring.

The recorded local no-network run on 2026-09-09 completed with **680 passed and
4 skipped** (`uv run --frozen pytest -q`). The skips were three explicitly
opt-in paid Provider cases and the optional PowerPoint desktop E2E test; neither
is part of the no-network CI gate. Run the commands above against the target
revision instead of using this dated count as a substitute for current evidence.
On the same revision, the shared candidate verifier reported zero Pyright errors,
built the Core wheel, and produced a Product bundle plus `SHA256SUMS`.

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
