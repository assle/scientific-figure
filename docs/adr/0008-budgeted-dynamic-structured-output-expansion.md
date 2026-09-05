---
status: accepted
---

# Expand structured output dynamically within the paid-call budget

OpenAI-compatible structured Model invocations start with a modest output allowance and double it only when the Provider returns `incomplete` with reason `max_output_tokens`. Each repeated invocation is recorded as another paid call and an auditable Structured output expansion; expansion stops when the response completes, the Provider reports another reason, or the Model role's call budget is exhausted.

A single large fixed allowance was rejected because ordinary responses do not need it and Provider limits differ. Silent retry inside the HTTP Adapter was rejected because it would hide paid calls from Run State and bypass the existing cost boundary.
