---
status: accepted
---

# Keep role routing provider-neutral while supporting native image dialects

Model routes remain bound to named Providers rather than vendors, but Provider types may include a narrowly scoped native wire dialect when a model capability is unavailable through OpenAI- or Anthropic-compatible APIs. DashScope Native is the first such type: it may serve only `image_generate` and inherited `image_edit`, uses the synchronous multimodal-generation endpoint, immediately downloads temporary result URLs, and cannot claim mask editing, structure control, native alpha, or batch-candidate support that the Core runtime does not implement.

Treating Qwen Image as OpenAI Compatible was rejected because its documented image API has a different request and response contract. Requiring a user-operated compatibility proxy was also rejected because it would move a core interoperability requirement outside the product and make Connection tests misleading.
