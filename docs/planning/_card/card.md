# Card — Local embeddings → fully-offline AI Copilot

> Freeform task (no GitHub issue). Slug: `local-embeddings-offline-copilot`. Type: `feat`.
> Branch: `feat/local-embeddings-offline-copilot`.

## Brief

Make the AI Copilot's query-template matching run on a local / OpenAI-compatible
(Ollama) embedding endpoint so a fully self-hosted, **keyless** install gets a
working Copilot — closing the gap left by the shipped local-LLM analysis batch.

Today the analysis pipeline can run entirely offline (Ollama / OpenAI-compatible,
keyless; falls back to VADER) — but the **Copilot template matcher still hard-depends
on OpenAI `text-embedding-3-small`**. A self-hoster with only a local model gets
analysis but a degraded/broken Copilot fast-path.

## Confirmed code facts (Phase 0 verification)

- `services/backend-api/src/services/copilot/template_matcher.py`
  - line ~25: `_EMBEDDING_DIMS = 1536` (hardcoded, OpenAI-shaped)
  - line ~100: `generate_embedding` → OpenAI `text-embedding-3-small` (1536 dims)
  - line ~112 `_call_embedding_api`: raises "No OpenAI API key configured for embeddings."
  - line ~55 `cosine_similarity`: similarity computed in Python over JSON arrays
- `services/backend-api/src/services/copilot/template_saver.py`
  - lines ~490–510 `_generate_embedding`: same OpenAI `text-embedding-3-small` call,
    raises "No OpenAI API key configured for embedding."
  - seeds system templates + auto-saves successful queries with embeddings
- `services/backend-api/src/models/query_template_mapping.py`
  - line ~15: `question_embedding = Column(JSON, nullable=True)` — stored as JSON array,
    **no pgvector** (so swapping providers needs no vector-column migration)
- `services/backend-api/src/api/routes/copilot_ws.py`
  - line ~554: template matching is a "fast path — may fail if no embeddings/tables"
    → there is already a degrade path when matching fails.

## Goal

Pluggable embedding provider for the Copilot, reusing the existing local-LLM /
OpenAI-compatible provider config that the analysis pipeline already uses. When no
embedding provider is configured, the Copilot must still answer via the LLM path
(template fast-match simply disabled) — mirroring the analyzer's VADER fallback.

## Known caveat (must design for up front)

Existing stored embeddings are OpenAI 1536-dim and **cannot** be cosine-compared
against local-model vectors (nomic-embed-text=768, all-MiniLM=384). Switching the
embedding provider therefore forces a **re-embed of every stored template** (system
seeds + auto-saved), and the hardcoded `_EMBEDDING_DIMS=1536` plus stored vectors must
become provider/model-aware (store model + dim alongside the vector; re-seed on
provider change; skip/fall back gracefully on mismatch). The provider swap itself is
small; the re-embed + dimension-awareness is the real work.

## Moat rationale (why this is the pick)

Completes the half-shipped local-LLM/self-host story (`AI-TRACKING.md` Open-Source
Feature Batch shipped the analysis side; `PRD-AI-COPILOT` documents the Copilot's
OpenAI-embedding dependency as a known limitation). Dead-center on the
public-API/local-LLM/self-host moat, and gets better as local embedding models improve.
