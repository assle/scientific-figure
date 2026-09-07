---
status: accepted
---

# Expand structured output dynamically within the paid-call budget

Structured Phase worker invocations start with 8,192 output tokens independently for Intake, Planning, and Review and repair. Provider/Model role `output_tokens` configuration can override the initial allowance per phase and supply a maximum. Non-phase vision requests retain their existing initial allowance. Responses `incomplete/max_output_tokens` and the equivalent Anthropic phase `stop_reason=max_tokens` are the only expansion signals.

Within one Run State, remember the highest actually dispatched Phase allowance keyed by phase, Provider ID and model. Resume the same key at the larger of its configured initial allowance and remembered allowance, capped at its effective maximum. Do not transfer allowances between phases, Providers, models, runs, or into image generation. Older saved states without explicit allowance history use configured defaults rather than inferring potentially ambiguous history.

Each repeat is another budgeted model call. The Provider client doubles the allowance within the same logical invocation deadline, clamping at the configured/documented ceiling and stopping when no increase remains. Check the role-call budget before dispatch; an unsent expansion is never recorded as used capacity. The Run Store atomically persists actual dispatch allowances with call counts. Numeric Provider usage, including reasoning tokens when supplied, is kept in attempt diagnostics; missing usage remains unknown and reasoning text is not logged.

A single large fixed allowance was rejected because ordinary responses do not need it and Provider limits differ. Silent retry inside the HTTP Adapter was rejected because it would hide paid calls from Run State and bypass the existing cost boundary.
