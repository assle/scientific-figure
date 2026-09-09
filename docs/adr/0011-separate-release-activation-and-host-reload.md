---
status: accepted
---

# Separate release, local activation, and host reload

Publishing, Local activation, and host reload are independent, verifiable, and
composable lifecycles. A convenience release command may orchestrate them, but
each lifecycle keeps its own idempotent implementation and result: a Published
release does not depend on local installation succeeding, Local activation owns
disk delivery and compensation, and host reload is the human safety boundary
that lets Codex or OpenCode replace in-memory Runtime instances without
interrupting active Provider work or unsaved Configuration drafts.

## Consequences

- Maintainer release automation prepares one canonical Product version, waits
  for authoritative CI, creates an immutable tag, and lets the tag workflow
  publish the complete Product bundle, Core artifact, Release manifest, and
  detached checksums.
- Local activation pins one Target version, verifies its Product bundle before
  execution, preserves configuration, credentials, projects, data, and run
  artifacts, and replaces product-owned Runtime, Plugin, Skill, launcher, GUI,
  and dependency files as one compensating Activation transaction.
- A Runtime referenced by a running MCP or GUI is protected from pruning.
  Previous product files are removed after Local version convergence; only ten
  rotated, redacted transaction logs remain.
- MCP and the Configuration app remain on-demand. Installation never introduces
  a product daemon, silently terminates a host, or starts every component.
- `scientific-figure status` is the single local authority for installed
  versions, running Runtime instances, cleanup state, and whether host reload is
  required. Remote Release comparison is explicit.
- The public delivery redesign ships together as Product version `0.6.0`.
  Existing installation aliases remain for at least one minor release with
  migration notices.

## Delivery sequence

1. Add the read-only local status model and process discovery.
2. Make CI build the Product bundle, Release manifest, checksums, and Core wheel.
3. Add exact-version download, offline bundle input, verification, and the
   Activation transaction.
4. Add Native plugin compensation, in-use Runtime protection, and convergence
   cleanup.
5. Add the new release, install, and update command surfaces with compatibility
   notices.
6. Pass clean install, upgrade, interruption, rollback, stale-process,
   cross-platform, and real Codex restart acceptance before releasing `0.6.0`.
