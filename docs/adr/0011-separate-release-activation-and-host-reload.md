---
status: accepted
---

# Separate release, local activation, and host reload

Publishing, Local activation, and host reload are independent, verifiable, and
composable lifecycles. A convenience release command may orchestrate them, but
each lifecycle keeps its own idempotent implementation and result: a Published
release does not depend on local installation succeeding, Local activation owns
disk delivery and compensation, and host reload is the human safety boundary
    that lets Codex replace Running runtime instances without
interrupting active Provider work or unsaved Configuration drafts.

## Consequences

- Maintainer release automation prepares one canonical Product version, waits
  for authoritative CI, creates an immutable tag, and lets the tag workflow
  publish the complete Product bundle, Core artifact, Release manifest, and
  detached checksums.
- Local activation pins one Target version, verifies its Product bundle before
  execution, preserves configuration, credentials, projects, data, and run
  artifacts, and replaces product-owned Core runtime, Native plugin, Workflow
  Skill, launcher, Configuration app, and dependency files as one compensating
  Activation transaction.
- A Core runtime referenced by a running Lifecycle MCP server or Configuration
  app is protected from pruning.
  Previous product files are removed after Local version convergence; only ten
  rotated, redacted transaction logs remain.
- The Lifecycle MCP server and Configuration app remain on-demand. Installation
  never introduces a product daemon, silently terminates a host, or starts every
  product component.
- `scientific-figure status` is the single local authority for installed
  versions, Running runtime instances, cleanup state, and whether host reload is
  required. Remote Release comparison is explicit.
- The public delivery redesign ships together as Product version `0.6.0`.
  Existing installation aliases remain for at least one minor release with
  migration notices.

## Delivery sequence

1. Add the read-only local status model and process discovery.
2. Make CI build the Product bundle, Release manifest, checksums, and Core wheel.
3. Add exact-version download, offline bundle input, verification, and the
   Activation transaction.
4. Add Native plugin compensation, In-use runtime protection, and convergence
   cleanup.
5. Add the new release, install, and update command surfaces with compatibility
   notices.
6. Pass clean install, upgrade, interruption, rollback, stale-process,
   cross-platform, and real Codex restart acceptance before releasing `0.6.0`.
