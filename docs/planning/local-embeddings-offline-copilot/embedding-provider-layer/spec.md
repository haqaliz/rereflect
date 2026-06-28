# Aspect Spec — embedding-provider-layer

**Parent PRD:** `../prd.md` · **Sequencing:** FOUNDATION — blocks `template-matching-local` and `copilot-llm-local`.

## Problem slice & outcome
A pluggable embeddings abstraction in **backend-api** (the Copilot's home) that produces a
`list[float]` from text via the org's configured provider — local/keyless or cloud BYOK —
reusing the existing config + BYOK plumbing. No embeddings concept exists anywhere today
(worker `llm/` is chat-only); this builds it, mirroring the worker LLM factory/resolver shape.

## In scope
- `EmbeddingProvider` interface + impls:
  - `openai` (BYOK key via `resolve_org_byok_key`; default model `text-embedding-3-small`, 1536)
  - `openai_compatible` (keyless; `base_url` from `OrgAIConfig`; model from config; e.g. Ollama, `nomic-embed-text`)
  - `google` (Gemini, e.g. `text-embedding-004`)
- `EmbeddingProviderFactory.create(provider, *, api_key, base_url, model)` dispatcher.
- An org resolver: `resolve_embedding_provider(org_id, db) -> (provider | None, dims)` that
  reads `OrgAIConfig` (`default_provider`, `base_url`, optional `model_embeddings`) and BYOK
  key, returning `None` when nothing is configured (degrade signal).
- Normalize all provider responses to `list[float]`; expose the embedding `dimension`.
- Reuse: `src/utils/byok.py`, `src/utils/encryption.py`, `OrgApiKey`, `OrgAIConfig`,
  the `_LOCAL_PROVIDERS` keyless+base_url pattern (mirror, don't import from worker).

## Out of scope
- Touching `template_matcher` / `template_saver` / `copilot_ws` (later aspects).
- The migration and seeding (in `template-matching-local`).
- Anthropic (no first-party embeddings API).
- Caching embeddings.

## Acceptance criteria (testable)
- AC1: `openai` provider returns a 1536-dim vector (mocked client) for given text.
- AC2: `openai_compatible` provider calls the configured `base_url` with **no api_key** and
  returns the model's native dims (mock a 768-dim response).
- AC3: `google` provider normalizes its response to `list[float]`.
- AC4: factory raises a clear error for an unknown provider; `resolve_embedding_provider`
  returns `(None, _)` when neither BYOK key nor local base_url is configured.
- AC5: provider/model/base_url/api_key are all injectable (no hardcoded model or client).

## Dependencies & sequencing
- None upstream. Must land first.

## Open questions / risks
- OQ1 (from PRD): shared module vs mirrored factory — default to **mirrored in backend-api**
  unless tech-plan finds a clean shared location; cross-service import is rejected.
- R4: Google embeddings request/response shape differs — provider impl owns normalization.
