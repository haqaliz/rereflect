# Aspect Spec — template-matching-local

**Parent PRD:** `../prd.md` · **Sequencing:** depends on `embedding-provider-layer`. Independent of `copilot-llm-local`.

## Problem slice & outcome
The Copilot's query→template fast-path generates and compares embeddings via the new
provider layer instead of a hardcoded OpenAI client, with provider/dimension-aware storage
so vectors are never compared across providers, and the 15 system templates are re-embedded
for the active provider automatically at startup.

## In scope
- **Matcher** (`template_matcher.py`): thread `provider/api_key/base_url/model` into
  `find_match` → `generate_embedding` → embedding call; remove the hardcoded OpenAI client
  and the global `_EMBEDDING_DIMS = 1536`; the matcher **skips mapping rows whose
  `embedding_provider`/`embedding_dimension` ≠ the active provider** before cosine compare.
  Keep the 0.85 threshold.
- **Saver** (`template_saver.py`): same threading for `_generate_embedding`, `save_template`,
  `seed_system_templates`; persist `embedding_provider` + `embedding_dimension` on every
  mapping written.
- **Migration** (Alembic): add `embedding_provider` (String(50)) + `embedding_dimension`
  (Int) to `query_template_mappings`. **Backfill from actual vector length:** `len==1536`
  → `('openai',1536)`; null/short/other → stale (excluded from matching). Index
  `(embedding_provider, embedding_dimension)` optional.
- **Startup seeding** (`main.py` lifespan): wire `TemplateSaver.seed_system_templates()`
  (currently never called — only ResponseTemplate is seeded). Make idempotency
  **provider+dim-aware**: if active provider/dim ≠ stored system-template vectors, re-embed
  the 15 system templates for the active provider. Must **not crash boot** if the embedding
  endpoint is unreachable — log + continue (degrade).
- **Lazy re-embed (S2)** of auto-saved org templates whose provider/dim is stale: re-embed
  on next access or mark inactive (finalize approach in plan).
- **Callers** (`copilot_ws.py`): pass resolved provider/key/base_url into `find_match` and
  `save_template` (the matching-side calls only; LLM-gen routing is `copilot-llm-local`).

## Out of scope
- Copilot LLM generation routing + the BYOK-required gate (→ `copilot-llm-local`).
- pgvector. Changing threshold or ranking.

## Acceptance criteria (testable)
- AC1: with a local provider configured, a question matching a system template returns it
  (cosine ≥ 0.85) using locally-generated embeddings (mocked).
- AC2: matcher skips rows whose provider/dim ≠ active; a 1536 OpenAI row is ignored when the
  active provider is 768-dim local, and vice versa — no cross-dim cosine is attempted.
- AC3: migration backfills existing 1536-len rows to `('openai',1536)` and marks a
  null/short-vector row stale; downgrade drops the columns.
- AC4: startup seeding re-embeds the 15 system templates when the active provider differs;
  idempotent on a second boot with the same provider (no duplicate re-embed).
- AC5: embedding endpoint unreachable at boot → app still starts; seeding logged as skipped.
- AC6: existing OpenAI-BYOK org behaviour unchanged (regression: 1536 rows still match).
- AC7: existing `test_template_matcher.py` (15) + `test_template_saver.py` (9) updated to be
  dimension/provider-parameterized and green.

## Dependencies & sequencing
- After `embedding-provider-layer`. Migration before seeding-change deploy.

## Open questions / risks
- R1: backfill correctness — covered by length-based rule (AC3).
- OQ2: stale org auto-saved templates — lazy re-embed vs deactivate; default lazy re-embed.
