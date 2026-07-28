# Ark interfaces

Volcengine Ark provider integration notes (plan sections 5, 8, 12, 17).

> Status: **to be verified and implemented in Phase 4.**
>
> Ark APIs and available models can change. Before implementing the provider
> client, verify the current official documentation, request schema,
> authentication requirements, model IDs, image-edit support, output retention,
> and rate limits. Keep updated API details in this file, not in the core Skill
> workflow.

## Authoritative references

- Volcengine Ark ImageGenerations API:
  https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01

## Required behaviors (from the plan)

- Fixed-role model configuration; four independent roles.
- Reference analysis returns structured panels, objects, text candidates,
  confidence values, and uncertainties.
- Image generation/edit produce one isolated object by default.
- Multimodal validation combines deterministic checks with the configured Ark
  validation model.
- Every paid call checks and updates the run budget.
- Upload disclosure: list all files that will be uploaded before approval.
- Rate-limit handling with exponential backoff.
- Cache key from model ID + prompt + parameters + reference hashes.
- Secrets never appear in logs or artifacts.
