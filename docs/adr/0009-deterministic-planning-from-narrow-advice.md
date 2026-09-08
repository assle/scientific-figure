---
status: accepted
---

# Build deterministic Figure plans from narrow Planning Advice

Model-backed Planning returns schema-governed Planning Advice for composition and style, while the Figure Planning Module deterministically derives the complete Figure plan from the approved Figure brief. Returning a model-authored replacement plan was rejected because prompts cannot reliably protect Generation identity, membership, routes, ownership, hashes, and source provenance, and reproducing those locked fields wastes structured-output capacity.

## Consequences

Planning Advice rejects unknown assets and semantic nodes before Generation. The public Lifecycle interface remains the test seam, and model Adapters may vary without gaining authority over deterministic plan invariants.
