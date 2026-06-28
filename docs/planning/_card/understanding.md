# Phase 2 — Understanding note

## What the task is really asking

Let a fully self-hosted, keyless install (local / OpenAI-compatible LLM, e.g. Ollama)
get a working AI Copilot. Today the Copilot is OpenAI-bound in **two** independent
places, both of which must be considered:

1. **Template-matching embeddings** (the stated slice) — `template_matcher.py` /
   `template_saver.py` hardcode OpenAI `text-embedding-3-small` (1536-dim) and raise
   if no OpenAI key. This is the query→template fast-path.
2. **⚠️ Copilot LLM generation itself** — `copilot_ws.py:521-541` resolves a BYOK key
   via `resolve_org_byok_key(...)` and **returns an error immediately if the key is
   None**, *before* template matching even runs. The Copilot's SQL/analysis/report
   generation uses its own OpenAI-BYOK client, **separate** from the analysis
   pipeline's local-capable provider chain (which lives in `worker-service/src/llm/`).

**Scope implication:** fixing only #1 makes *template matching* local but a keyless org
still can't use the Copilot at all, because #2 bails first. "Fully offline Copilot" =
both must route through the local-capable provider. This is the key scope decision for
the interview / review gate.

## Affected areas (services + files)

### backend-api (primary)
- `src/services/copilot/template_matcher.py` — `_EMBEDDING_DIMS=1536` (L25),
  `generate_embedding` (L97), `_call_embedding_api` → OpenAI `text-embedding-3-small`
  (L112-134), `cosine_similarity` over JSON arrays (L55), threshold `0.85` (L22).
  `find_match()` (L138) has **no api_key/provider param** — must thread through.
- `src/services/copilot/template_saver.py` — `_generate_embedding` OpenAI (L490-510);
  `save_template` (L351), `seed_system_templates` (L448), `SYSTEM_TEMPLATES` 15 defs
  (L64-338). Seeder idempotent **by SQL match** (L454) → won't re-embed on provider
  change unless made provider-aware.
- `src/api/routes/copilot_ws.py` — resolves BYOK key + bails if None (L521-541);
  calls `find_match` without api_key (L557-560); auto-saves templates (L788-798).
- `src/models/query_template_mapping.py` — `question_embedding = Column(JSON)` (L15),
  **no provider/dim recorded**, no pgvector (TODO only).
- `src/models/org_ai_config.py` — **already has `base_url` (L16)**, `default_provider`,
  `model_*` columns. Reuse; likely add `model_embeddings`.
- `src/utils/byok.py` (`resolve_org_byok_key`), `src/utils/encryption.py`
  (`decrypt_api_key`, `LLM_ENCRYPTION_KEY`), `src/models/org_api_key.py` — BYOK plumbing
  already in backend-api. **No embeddings abstraction exists anywhere yet.**
- `src/api/main.py` — startup lifespan seeds **ResponseTemplate only** (L80);
  `TemplateSaver.seed_system_templates()` (the QueryTemplate seeder) is **never wired
  at startup** — only called in tests. So the 15 system query-templates may not be
  seeded in prod at all.

### worker-service (reference pattern to mirror, NOT to import directly)
- `src/llm/factory.py` — `LLMProviderFactory.create()` dispatches openai / anthropic /
  google / ollama / openai_compatible; `_OLLAMA_DEFAULT_BASE_URL="http://localhost:11434/v1"`.
- `src/llm/org_resolver.py` — `build_fallback_chain` (L84) with `_LOCAL_PROVIDERS`
  (ollama, openai_compatible) keyless path requiring `base_url` (L114-127); BYOK decrypt
  (L129-152). Mirrors the VADER-style graceful fallback. **Gap noted:** `call_llm_for_org`
  doesn't extract `base_url` from OrgAIConfig.
- No embeddings types exist (`types.py` is chat-only).

## Migration / re-embed surface

- New Alembic migration on `query_template_mappings`: add `embedding_provider`
  (String, default `'openai'`) + `embedding_dimension` (Int, default `1536`); backfill
  existing rows. No pgvector needed (stays JSON; cosine in Python).
- Cross-provider vectors are incomparable. On provider change: matcher must **ignore
  mismatched-provider rows** (degrade to LLM path) and the seeder must **re-embed**
  system templates for the active provider (make idempotency provider-aware, not
  SQL-only). Auto-saved org templates: re-embed lazily or mark stale.

## Tests to extend (TDD)
- `tests/test_template_matcher.py` (15 tests; hardcode `[0.1]*1536`).
- `tests/test_template_saver.py` (9 tests; `seed_system_templates` mocks `[0.1]*1536`).
- Both must be parameterized for variable dims / provider.

## Open questions for the interview
1. **Scope: embeddings-only or full offline Copilot?** Does this slice also route the
   Copilot's *LLM generation* (`copilot_ws.py`) through the local-capable provider, or
   only the template-matching embeddings? (Embeddings-only leaves keyless orgs still
   unable to use the Copilot.)
2. **Embedding providers to support:** OpenAI + OpenAI-compatible/Ollama only (Anthropic
   has no first-party embeddings API; Google optional)?
3. **Re-embed trigger on provider switch:** lazy/ignore-mismatch + provider-aware
   re-seed at startup, vs. an explicit admin "rebuild embeddings" action?
4. **No-embedding-provider behavior:** confirm degrade = Copilot answers via LLM path
   with template fast-match disabled (mirror VADER fallback).
