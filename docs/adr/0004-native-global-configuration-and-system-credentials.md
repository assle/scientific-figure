---
status: accepted
---

# Use a native global configuration app and system credential store

Scientific Figure Builder will provide a native PySide6 Configuration app that manages only Global configuration: Model routes, Providers, and Provider credentials. It will not configure the Calling Agent, edit Project configuration, or become a task-running console. Provider credentials entered through the app will be stored in the operating system's System credential store and referenced from configuration by a stable, non-secret `credential_id`; Environment-backed credentials remain supported for headless hosts, CI, existing installations, and portable project workflows.

This decision extends ADR-0003's Provider-neutral routing. A Provider remains vendor-neutral and identified independently from its credential, so renaming a Provider ID does not require moving its Keyring-backed credential. Credential resolution prefers an available Keyring-backed credential and otherwise checks the existing Environment-backed source. The application refuses to save a new credential when no secure system backend is available rather than falling back to a plaintext file.

## Considered options

- **Native PySide6 app (chosen)** — one Python implementation can ship with the existing private runtime and provide a desktop experience on macOS, Windows, and Linux without a browser, local port, or Node.js toolchain.
- **Local web application** — rejected because configuration would require a browser and listening server, expanding the security and lifecycle surface for a small local task.
- **Electron or Tauri** — rejected because a second frontend toolchain and runtime would outweigh the scope of the configuration workflow.
- **Store secrets in YAML or an application secrets file** — rejected because configuration copying, diagnostics, backups, and support workflows would expose or duplicate Provider credentials.
- **Environment variables only** — retained as a compatibility path but rejected as the only interaction because replacing credentials and configuring several Providers is cumbersome and error-prone for desktop users.

## Consequences

The default desktop-capable installation becomes larger because it includes Qt, while non-GUI code paths must remain free of eager Qt imports. Linux desktop credential writes depend on an available secure Keyring backend; headless use remains supported through Environment-backed credentials. Global configuration and the System credential store are separate persistence systems, so implementations can guarantee atomic configuration replacement and compensating credential operations, but not a single cross-store transaction.
