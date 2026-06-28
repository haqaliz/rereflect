# PRD — Local Embeddings & Fully-Offline AI Copilot

**Slug:** `local-embeddings-offline-copilot`
**Branch:** `feat/local-embeddings-offline-copilot`
**Status:** Draft (pre review-gate)
**Author:** Rereflect (via rereflect-begin-fast)
**Source:** Freeform task — see `docs/planning/_card/card.md` + `understanding.md`

---

## Problem Statement

Rereflect pivoted to open-source, self-hosted, BYOK/local-LLM (MIT, all features
unlocked). The analysis pipeline already runs **fully offline** — Ollama or any
OpenAI-compatible endpoint, keyless, with a VADER fallback when no model is configured
(`worker-service/src/llm/`). The **AI Copilot does not.** It is OpenAI-bound in two
independent places:

1. **Template-matching embeddings** — `template_matcher.py` and `template_saver.py`
   hardcode OpenAI `text-embedding-3-small` (1536-dim) and raise
   `"No OpenAI API key configured for embeddings"` if no OpenAI key exists.
2. **Copilot answer-generation** — `copilot_ws.py:521-541` resolves a per-org BYOK key
   and **returns an error immediately if it is `None`**, before any matching runs. The
   Copilot's NL→SQL / analysis / report generation uses its own OpenAI-BYOK client,
   *separate* from the analysis pipeline's local-capable provider chain.

**Consequence:** a self-hoster running a local model (the headline OSS use case) gets a
hard error the moment they open the Copilot. `PRD-AI-COPILOT` documents this as a known
limitation. This is the single biggest gap between "the analysis side runs offline" and
"the product runs offline."

**Evidence it's real:** confirmed in code (Phase 0 + Phase 2 dig, file:line cited in
`understanding.md`); called out as a documented limitation in `PRD-AI-COPILOT`; aligns
with `AI-TRACKING.md` "Open-Source Feature Batch" which shipped the *analysis* offline
path but not the Copilot's.

## Goals & Success Metrics

| Goal | Metric |
|---|---|
| A keyless local-LLM org can use the Copilot end-to-end | Open Copilot, run a data query + an analysis query against a configured local provider (Ollama / OpenAI-compatible) with **no** OpenAI key present → both return answers, no error |
| Template fast-path works on local embeddings | A question matching a system template returns the template result (cosine ≥ 0.85) using locally-generated embeddings |
| Graceful degrade, never a hard failure | With no embedding provider available, Copilot still answers via the LLM path; template fast-match is silently skipped (mirrors VADER fallback) |
| No regression for cloud BYOK orgs | Existing OpenAI-BYOK Copilot behaviour unchanged; existing 1536-dim stored embeddings still match |
| Provider switch is self-healing | After changing the active provider, system templates are usable again with **zero** admin action |
| SQL safety holds for any provider | The NL→SQL safety validator (read-only, org-scoped, 3-join max, schema whitelist, 5s timeout) runs **unconditionally** on all generated SQL regardless of provider; a malicious/local-model SQL string is still rejected |

### Answer-quality stance (explicit non-goal vs. guardrail)

Local-model **answer quality is operator-dependent** and is a **stated non-goal** of this
slice — a weak 7B model may produce a weaker NL→SQL or analysis answer than GPT-4o, and
that is acceptable and honest to the OSS brand. What is **in scope** is that the degraded
experience is *safe and legible*, not silently broken:
- **Quality guardrail (testable):** on a fixed set of ~10 canned questions, the local path
  must produce **syntactically valid, org-scoped SQL that passes the existing safety
  validator** ≥ 70% of the time against a reference local model; questions that fail
  validation must fall through to a clear "couldn't answer that one" path, never an
  unhandled error or unsafe SQL.
- **Weak-model UX:** when generation fails validation or returns empty, the user sees an
  honest "I couldn't turn that into a safe query with the current model" message (with a
  hint that a stronger model improves results), **not** a stack trace or a wrong-but-
  confident answer.

## User Personas & Scenarios

- **Self-hoster (keyless, local model)** — runs Rereflect + Ollama on their own infra,
  no cloud API keys. Wants the Copilot to "just work" like the rest of the product.
- **Self-hoster (OpenAI-compatible gateway)** — points `base_url` at vLLM / LM Studio /
  LocalAI. Same expectation.
- **Cloud BYOK org (existing)** — keeps using OpenAI; must see no change or breakage.

## Requirements

### Must-have
- **M1 — Embedding provider abstraction (backend-api).** A pluggable embeddings layer
  mirroring the worker LLM factory/resolver pattern, living in backend-api (the Copilot's
  home), reusing backend-api's existing BYOK plumbing (`byok.resolve_org_byok_key`,
  `encryption.decrypt_api_key`, `OrgApiKey`, `OrgAIConfig.base_url`). Providers:
  - `openai` (cloud BYOK, default model `text-embedding-3-small`)
  - `openai_compatible` (keyless, `base_url` from `OrgAIConfig`, e.g. Ollama
    `http://localhost:11434/v1`, model from config)
  - `google` (Gemini, e.g. `text-embedding-004`)
  - Anthropic explicitly **N/A** (no first-party embeddings API).
- **M2 — Route template matching through the abstraction.** Thread provider + api_key +
  base_url + model into `TemplateMatcher.find_match` / `generate_embedding` /
  `_call_embedding_api`; remove the hardcoded OpenAI client and the hardcoded
  `_EMBEDDING_DIMS = 1536` (dimension becomes provider-derived / validated against stored
  metadata, not a global constant).
- **M3 — Route template saving + seeding through the abstraction.** Same threading for
  `TemplateSaver._generate_embedding`, `save_template`, `seed_system_templates`.
- **M4 — Route Copilot answer-generation through the local-capable provider.** Replace
  the "BYOK key required → error" gate in `copilot_ws.py:521-541` so NL→SQL / analysis /
  report generation use the local-capable provider chain (local/keyless or cloud BYOK),
  matching the analysis pipeline's selection logic. A keyless local org no longer errors.
- **M5 — Provider/dimension-aware storage.** Alembic migration adding
  `embedding_provider` (String, default `'openai'`) + `embedding_dimension` (Int) to
  `query_template_mappings`. **Backfill from the actual stored vector length, not a blind
  default:** rows where `len(question_embedding) == 1536` → `('openai', 1536)`; rows with
  a null/short/wrong-length vector → marked stale (null provider/dim or `is_active`-style
  exclusion) so the matcher never compares a junk vector. Stays JSON + Python cosine (no
  pgvector).
- **M6 — Auto-reconcile on startup.** Wire `TemplateSaver.seed_system_templates()` into
  the app lifespan (it is currently **never called at startup** — only ResponseTemplate
  seeding is). Make seeding **provider-aware**: when the active embedding provider/dim
  differs from stored system-template vectors, re-embed the 15 system templates for the
  active provider (idempotency keyed on provider+dim, not SQL-only). The matcher **skips
  rows whose provider/dim ≠ active provider** so cross-provider vectors are never compared.
- **M7 — Graceful degrade.** No embedding provider resolvable → Copilot still answers via
  the LLM path; template fast-match is skipped without surfacing an error.

### Should-have
- **S1 — `model_embeddings` column on `OrgAIConfig`** for explicit per-org embedding-model
  override (default derived from provider). **Apply to both the backend-api model and the
  worker-service `OrgAIConfig` mirror** to avoid schema drift.
- **S0 — Provider-agnostic SQL safety (verified).** Confirm the existing NL→SQL safety
  validator runs unconditionally on all generated SQL and add a test proving a
  malicious/local-model SQL string is rejected (paired with success-metric row above).
- **S4 — Docs/README update** ("the AI Copilot now runs fully offline on a local model")
  so the moat actually lands with self-hosters; cross-link from `PRD-AI-COPILOT`'s known
  limitation and `AI-TRACKING.md`.
- **S2 — Lazy re-embed of auto-saved org templates** whose provider/dim is stale (re-embed
  on next access or mark inactive), so org-specific learned templates survive a switch.
- **S3 — AI Settings surfacing** of the embedding provider/model + a read-only "system
  templates: N embedded for provider X" status line.

### Nice-to-have
- **N1 — Admin "Rebuild embeddings" action** as a manual escape hatch (the auto path is
  the default per the interview).
- **N2 — Backfill safety log** at startup reporting how many templates were re-embedded /
  skipped.

## Technical Considerations

- **Services changed:** primarily `services/backend-api` (Copilot lives here, and the BYOK
  + OrgAIConfig plumbing is already here). The worker `llm/` package is the **reference
  pattern**, not an import target — duplicating the small factory/resolver shape in
  backend-api is cleaner than cross-service coupling. (Confirm during tech-plan whether a
  shared module is warranted vs. mirrored.)
- **Reuse, don't reinvent:** `OrgAIConfig.base_url` (already exists, L16), `default_provider`,
  `model_*`; `_LOCAL_PROVIDERS` keyless+base_url pattern; `resolve_org_byok_key`;
  `decrypt_api_key` / `LLM_ENCRYPTION_KEY`.
- **Multi-tenancy:** all paths already `organization_id`-scoped (templates, OrgAIConfig,
  OrgApiKey). System templates are `organization_id IS NULL` (global) — re-seed touches
  only `created_by='system'` rows.
- **Migration:** additive columns + backfill; no pgvector. Existing 1536-dim OpenAI rows
  keep matching for cloud BYOK orgs.
- **Startup ordering:** seeding must run after migrations in the lifespan; must be cheap /
  idempotent and not block boot if the embedding provider is unreachable (degrade, log,
  continue).
- **Tests (TDD):** extend `tests/test_template_matcher.py` (15) and
  `tests/test_template_saver.py` (9); both currently hardcode `[0.1]*1536` and must be
  parameterized for variable dims + provider. New tests for the embeddings factory/resolver,
  the migration, provider-aware seeding/skip logic, and the `copilot_ws` provider routing +
  keyless degrade.

## Data Model

`query_template_mappings` (add):
- `embedding_provider VARCHAR(50) NOT NULL DEFAULT 'openai'`
- `embedding_dimension INTEGER NOT NULL DEFAULT 1536`
- (optional) index `(embedding_provider, embedding_dimension)`

`org_ai_config` (should-have S1): `model_embeddings VARCHAR(100) NULL`.

## Risks & Open Questions

- **R1 — Cross-provider incomparability (designed-for).** Mitigated by provider/dim
  columns + matcher skip + provider-aware re-seed. Risk if backfill default is wrong →
  verify all pre-existing rows are genuinely OpenAI/1536 (they are: only OpenAI path existed).
- **R2 — Copilot LLM path is larger than embeddings (M4).** `copilot_ws.py` generation may
  assume OpenAI-specific behaviour (function calling, JSON mode, streaming token shape).
  Local models vary. Open question for tech-plan: does NL→SQL/report generation rely on
  OpenAI-only features, and what's the local-model quality floor? Degrade path must hold.
- **R3 — Startup re-embed cost / reachability.** If the local endpoint is down at boot,
  seeding must not crash the app. Re-embed of 15 templates × N patterns is small but not free.
- **R4 — Google embeddings shape** differs from OpenAI (request/response, dims). Provider
  impl must normalize to `list[float]`.
- **OQ1 — Shared module vs mirrored factory** (tech-plan decides).
- **OQ2 — Stale org auto-saved templates** (S2): lazy re-embed vs deactivate — finalize in spec.

## Out of Scope

- pgvector / a real vector store (stays JSON + Python cosine).
- Anthropic embeddings (no first-party API).
- Re-embedding/ô semantic search beyond the Copilot template-matching + generation paths
  (e.g. no new embedding-powered features).
- Changing the 0.85 match threshold or the template ranking algorithm.
- Fine-tuning / per-org embedding models.
- Frontend redesign of the Copilot UI (only minimal AI-Settings surfacing in S3).
