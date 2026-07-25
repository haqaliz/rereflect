# Phase 2 Understanding — local-embedding-quality (M5.4)

**What the task is really asking:** improve the *quality* of local (offline) embeddings used by the
AI Copilot's template matching — the quality dimension that `local-embeddings-offline-copilot`
deliberately deferred (that initiative shipped the plumbing and stated answer-quality was a
non-goal). Roadmap: `AI-TRACKING.md` M5.4, `[ ]` "parked / nice-to-have", no blocker.

## Affected area — entirely `services/backend-api/src` (worker has zero embedding consumers)

The pluggable seam already exists and every consumer goes through it:
- `services/backend-api/src/services/embeddings/` — `EmbeddingProvider` ABC (`base.py`: `embed()`,
  `dimension`), `EmbeddingProviderFactory.create()` (`factory.py`), `resolve_embedding_provider(org_id, db)`
  (`resolver.py`) → `ResolvedEmbedder(provider, embedder, dimension_hint)`.
- Providers: `openai` (cloud, 1536), `google` (cloud, 768), `openai_compatible` + `ollama` alias
  (HTTP to a self-hosted server; default `nomic-embed-text`).
- Config: `OrgAIConfig.default_provider` / `base_url` / `model_embeddings`
  (`src/models/org_ai_config.py`).
- Settings: `GET/PATCH /api/v1/settings/ai`, `GET /api/v1/settings/ai/embeddings/status`,
  `_default_embedding_model(provider)` + `EmbeddingStatusResponse` (`src/api/routes/ai_settings.py`).
- Consumers: `copilot_ws.py` (per-query match/save), `main.py` lifespan
  `seed_copilot_system_templates` (uses org #1 as global config), `services/copilot/template_matcher.py`
  (in-process Python cosine, threshold `0.85`, single argmax — no top-k, no pgvector, JSON-column vectors),
  `services/copilot/template_saver.py` (stores `question_embedding` JSON + `embedding_provider` +
  `embedding_dimension = len(vector)` per row).

## Finding 1 — there is NO in-process local embedding provider (scope-defining)

Only cloud (openai/google) and HTTP-delegated "local" (ollama/openai_compatible → external server)
exist. No `sentence-transformers`/ONNX/`torch` embedding path is imported anywhere; the one
`sentence-transformers==3.2.0` dep lives in **analysis-engine** and is **unused**. The brief's
"CPU-only / air-gappable / pre-baked model-cache like M5.1" implies **building a new in-process
provider**, which is a much bigger lift than changing a default model string. → central interview
question (Option A: new in-process provider, vs Option B: better default model on the existing
HTTP-local path).

## Finding 2 — model-swap staleness hole (the one correctness risk)

`TemplateMatcher.find_match` skip-filters stored rows on `(embedding_provider, embedding_dimension)`
only — NOT model name (`template_matcher.py:196-201`). So upgrading the model under the SAME provider
string at the SAME dimension (e.g. `nomic-embed-text` → another 768-dim model on `ollama`) yields
stale vectors that PASS the filter and get cosine-compared in an incompatible space → silent garbage
matches. `model_embeddings` exists on `OrgAIConfig` but is not part of the mapping's stored key.
Auto-reseed heals only the 15 system templates (provider-aware), never org-saved templates. Any
"better model" change MUST design for this (add model to the key / re-embed / invalidate).

## Finding 3 — mirror M5.1 (`local-analyzer-sentiment-model`), don't reinvent

- **eval-harness-and-card**: committed labeled fixtures + offline eval script + committed JSON
  artifact + read-only `GET .../accuracy` endpoint + frontend card; **disclosure, not a CI gate**;
  `has_results:false` (200) when absent; always shows `n`. M5.4 analog: a retrieval-quality eval
  (recall@k / MRR / match-rate at 0.85) hung beside the existing `/embeddings/status`.
- **model-packaging**: Dockerfile ARG-gated pre-bake (`BAKE_..._MODEL=false` default → zero network /
  zero weight bytes; `--build-arg ...=true` bakes for air-gap), `HF_HOME`, `HF_HUB_OFFLINE`/
  `TRANSFORMERS_OFFLINE`, documented in `docs/SELF_HOSTING.md`.

## Already shipped — do NOT rebuild

The whole embeddings package, resolver, provider/dim-tagged stored vectors, skip-filter,
provider-aware system-template reseed, and `/embeddings/status` endpoint. Quality was the explicit
non-goal — that is exactly M5.4's gap.

## Contradictions / honesty flags

- "Better local embedding model, plugged into the existing layer" (brief) reads as a swap, but the
  code shows the *genuinely* air-gappable in-process path doesn't exist yet — so the honest scope is
  either build it (A) or reframe "local" as the operator-run Ollama server (B). Must be resolved, not
  papered over.
- Honest brand: prior initiative capped its claim at "≥70% of canned questions yield safe SQL" and
  called quality "operator-dependent." M5.4 must claim only "measurably better retrieval on a stated
  offline eval set," never an absolute accuracy number.
- Avoid `status-sync-realtime-mapping` and `feat/classifier-model-versioning-rollback` (both in flight).

## Open questions for the interview

1. **Scope**: Option A (new in-process CPU embedding provider — true single-image air-gap, heavier
   dep) vs Option B (better default model for the existing Ollama/openai_compatible HTTP path — light,
   but "local" still needs an external server). This is the user's call; it changes scope massively.
2. If A: which model family (sentence-transformers `bge-small`/`all-MiniLM`/`gte-small` vs an ONNX
   runtime path) — size/latency/quality trade-off on CPU.
3. How to fix the staleness hole: add model name to the stored key + skip-filter, lazy re-embed on
   mismatch, or force a reseed? (Correctness requirement regardless of A/B.)
4. Eval metric + dataset: recall@k / MRR / match-rate at 0.85; where do labeled query→template pairs
   come from (hand-authored fixtures over the 15 system templates)?
5. Default-change policy: is the better model opt-in (byte-stable default preserved) or the new
   default? Brief says keep current default byte-stable → new model is opt-in.
