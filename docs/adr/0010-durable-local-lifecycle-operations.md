---
status: accepted
---

# Observe long Lifecycle advances through durable local operations

The Lifecycle MCP Adapter persists one locally owned phase operation per run and returns an in-progress result when a host stops waiting before the operation completes. Polling consumes the same local result without resubmission; if the local owner disappears, the outcome becomes unknown because a Provider response ID is not assumed to be a resumable remote job.

## Consequences

Operation ownership is claimed before dispatch, Provider call accounting remains authoritative in Run State, and completed Phase artifacts commit exactly once. Fast completion and failure retain their existing synchronous outcomes, while long work remains observable across separate tool calls.
