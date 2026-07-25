# PRD — Local Embedding Quality (M5.4)

**Slug:** `local-embedding-quality`
**Branch:** `feat/local-embedding-quality`
**Type:** feat (freeform, from `rereflect-next`) · **Date:** 2026-07-24
**Roadmap:** `AI-TRACKING.md` — **M5.4 "Local embedding quality"** (`[ ]` "parked / nice-to-have", no blocker)
**Status:** Draft for review-gate approval

---

## Problem Statement

Rereflect's AI Copilot matches a user's natural-language question against stored **query templates**
(canned SQL) using embeddings, and only falls through to LLM NL→SQL when no template clears the
`0.85` cosine threshold. That template-matching is the offline Copilot's fast path and its main lever
for running well **without** a cloud LLM key.

Two problems today:

1. **There is no genuinely local, in-process embedding model.** "Local" currently means the
   `ollama` / `openai_compatible` provider — an HTTP call to an inference server the operator must
   **run separately**. There is no CPU, in-process, single-image, air-gappable embedding path. The
   prior `local-embeddings-offline-copilot` initiative shipped the plumbing but **explicitly deferred
   answer quality** as a non-goal ("operator-dependent"). M5.4 is that deferred quality dimension.
2. **A model change silently corrupts matches.** `TemplateMatcher.find_match` skip-filters stored
   template vectors on `(embedding_provider, embedding_dimension)` **only — not the model name**. So
   swapping the model under the same provider string at the same dimension compares old and new
   vectors in incompatible spaces and returns garbage matches, and the auto-reseed heals only the 15
   system templates, never org-saved ones.

**Who has the problem:** self-hosting operators who want stronger offline Copilot retrieval without
standing up and maintaining a separate Ollama/vLLM server — the core OSS/self-hosted/BYOK audience.
Today their only "better than nothing" local option is running that external server.

**Evidence it's real:** grep confirms no `sentence-transformers`/ONNX embedding import anywhere in
`services/backend-api/src`; the one `sentence-transformers==3.2.0` dep lives in `analysis-engine` and
is unused. The staleness hole is visible at `services/backend-api/src/services/copilot/template_matcher.py:196-201`.

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| A real in-process local embedding option | Fresh `backend-api` install with no external inference server + no cloud key can select the `local` provider and the Copilot template-matcher returns matches | Works with **zero** external server and **zero** network at runtime |
| Prove the local model is better, honestly | Retrieval quality of the new local model vs the current local baseline (`nomic-embed-text` via Ollama) on a **committed** labeled query→template eval set | New local model beats baseline by a **meaningful margin** — recall@1 **≥ baseline + 0.05** (the claim) — **and does not regress** false-match rate on negatives (≤ baseline), offline. **Floor: ≥ 60 labeled query→template pairs** (incl. negatives); the card states `n`. A sub-threshold result is surfaced honestly and escalated, not massaged. |
| Zero regression / byte-stable default | Behaviour of an install that does **not** opt in (provider unset or `openai`/`google`/`ollama`) | **Identical** to today (characterization-tested); no default changes silently |
| No silent cross-space matching | After any embedding-model change, `find_match` never compares vectors from different models | Skip-filter keys on `(provider, dimension, model)`; system templates auto-re-embed; org rows skip-until-overwrite (never a wrong-space match) |
| Works offline / air-gapped | Image built with the pre-bake ARG runs the local model with `HF_HUB_OFFLINE=1` | No network call at runtime; documented pre-bake + offline path |
| Better default recommendation for the HTTP-local path | `SELF_HOSTING.md` recommends a stronger Ollama embedding model than `nomic-embed-text`, backed by the same eval | Recommendation is eval-backed, not asserted |

**Non-goal metric:** we do **not** publish an absolute accuracy/quality number as marketing — only
"measurably beats the local baseline on a stated offline eval set," matching the honest brand (churn
is already described as "a calibrated heuristic"; the prior copilot initiative capped its claim at
"≥70% of canned questions yield safe SQL").

## User Personas & Scenarios

- **Self-hosting operator, no external LLM infra (primary):** In Settings → AI, picks
  **Embedding provider → Local (in-process)**. New template embeddings + query embeddings are
  computed in-process on CPU; the offline Copilot's fast path improves with no Ollama server and no
  cloud key. The embeddings **status/accuracy card** shows recall@k / MRR vs the local baseline with
  `n`.
- **Air-gapped operator:** Builds the `backend-api` image with `--build-arg BAKE_EMBEDDING_MODEL=true`
  so the model weights are pre-baked; sets `HF_HUB_OFFLINE=1`; the local provider runs with no
  outbound network.
- **Operator already running Ollama:** Reads `SELF_HOSTING.md`, switches the recommended embedding
  model from `nomic-embed-text` to the eval-backed stronger model, and (because the staleness fix
  now keys on model) the system templates auto-re-embed instead of silently mis-matching.

## Requirements

### Must-have
1. **In-process local embedding provider** (`local`) implementing the existing `EmbeddingProvider`
   ABC (`embed()` + model-derived `dimension`), added to `EmbeddingProviderFactory`, the resolver's
   `_LOCAL_PROVIDERS`, and `VALID_PROVIDERS`/`LOCAL_PROVIDERS`/`_default_embedding_model` in
   `ai_settings.py`. Keyless, no `base_url` required. A deps-availability guard (mirroring
   `_sentiment_transformer_deps_available()`) makes the PATCH endpoint reject `local` when the lib is
   absent — no import-time crash for installs that never opt in.
2. **Model-swap staleness fix.** Add `embedding_model` to `query_template_mappings` (migration,
   backfill NULL = stale), include it in `find_match`'s skip-filter and in the stored mapping key,
   and make `seed_system_templates` re-embed on model change. Org-saved rows with a stale model are
   skipped (never wrong-space-matched) until overwritten. **This is a correctness requirement for the
   whole feature, not just Option A.**
3. **Byte-stable default.** No install that doesn't explicitly select `local` changes behaviour.
   Current per-provider defaults (`openai`/`google`/`ollama`) unchanged.
4. **Committed offline retrieval eval + read-only card.** A CLI eval (`scripts/eval_embeddings.py`,
   importable core) runs providers over committed labeled query→template fixtures, writes a committed
   JSON artifact, exposed via a read-only endpoint beside `GET /api/v1/settings/ai/embeddings/status`
   and a frontend card. Disclosure, **not** a CI merge gate; endpoint returns `has_results:false`
   (200) when the artifact is absent; always shows `n` and an honest "beats / does not beat" badge.
5. **Offline packaging.** `HF_HOME` wired, CPU-only wheels, a build-time pre-bake gated by
   `ARG BAKE_EMBEDDING_MODEL=false` (default = zero network / zero weight bytes), plus
   `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` documented in `docs/SELF_HOSTING.md`.

### Should-have
6. **Ollama default-recommendation bump (Option B).** Update `SELF_HOSTING.md` (and, if agreed, the
   `_default_embedding_model('ollama')` string) to a stronger, eval-backed model than
   `nomic-embed-text`, with the pull command. Small add-on; depends on the eval existing.

### Nice-to-have
7. **Lazy re-embed of org-saved templates** on `(provider, dimension, model)` mismatch, so org
   templates recover automatically instead of going dark until overwritten. (Deferred by default per
   the staleness decision — skip-until-overwrite is the accepted behaviour.)

## Technical Considerations

- **Services changed:** `services/backend-api` only (new provider, factory/resolver/settings wiring,
  migration on `query_template_mappings`, matcher/saver skip-filter+key, eval script + endpoint,
  Dockerfile). `services/frontend-web` (accuracy card + provider option in AI settings). **No worker
  changes** except mirroring the new `embedding_model` column on the worker's `OrgAIConfig`/mapping
  model **only if** the worker model mirrors it for schema parity — verify; the worker has zero
  embedding consumers.
- **Model choice (recommendation, final pick in tech-plan):** a small CPU sentence-transformers model
  — `BAAI/bge-small-en-v1.5` (384-dim, ~130 MB, strong MTEB for its class) preferred, with
  `sentence-transformers/all-MiniLM-L6-v2` (384-dim, ~90 MB) as the lighter fallback. Ollama bump:
  `mxbai-embed-large` or `bge-m3` vs keeping `nomic-embed-text` — decided by the eval.
- **Multi-tenancy:** embedding selection is per-org via `OrgAIConfig.default_provider` +
  `model_embeddings`; system templates use org #1 as the de-facto global config (existing pattern).
  No new cross-tenant surface.
- **Dependency weight:** adds `sentence-transformers` (+ `torch`, already declared for M5.1's
  transformer sentiment but currently unused in backend-api) to `backend-api/requirements.txt`. This
  is a real image-size / cold-start cost — mitigated by lazy import + the default-off pre-bake ARG.
- **Storage:** vectors stay JSON-column + in-process Python cosine (pgvector remains out of scope, as
  in the prior initiative). A 384-dim local model produces *smaller* stored vectors than 768/1536 —
  neutral-to-positive on storage.

### Data Model (Alembic)
- `query_template_mappings`: **+ `embedding_model` `String(100)` nullable** (NULL = stale/pre-migration,
  skipped by `find_match`). Backfill leaves existing rows NULL (they re-embed on next seed / are
  skipped). Index: extend or add to cover `(embedding_provider, embedding_dimension, embedding_model)`.
- `OrgAIConfig`: no new column (`model_embeddings` already exists and is reused as the selected local
  model id).

### API Contracts (FastAPI)
- New read-only `GET /api/v1/settings/ai/embeddings/accuracy` (mirrors the M5.1
  `.../sentiment/accuracy`): returns the committed eval artifact or `has_results:false`.
- `GET /api/v1/settings/ai/embeddings/status`: extend to also report the selected `embedding_model`.
- `PATCH /api/v1/settings/ai`: accept `local` as a provider; reject when deps absent.

### Non-Functional
- **Async safety:** the in-process `embed()` is CPU-bound and MUST run off the event loop (via the
  matcher's existing `run_in_threadpool`/executor path) so it never blocks the async WS handler.
- **First-load latency:** model load is one-time and can be multi-second — it MUST be lazy-cached AND
  **pre-warmed at startup when `local` is the selected provider** (so the first real query doesn't eat
  the load). Never load the model at import time.
- Target: single-query embed well under the existing `10s` local-endpoint timeout budget; measure and
  document steady-state per-query latency and the one-time load cost.

## Risks & Open Questions

- **R1 — Honest proof is the hard part.** Retrieval quality is harder to benchmark than sentiment
  macro-F1. Mitigation: hand-authored query→template fixtures over the 15 system templates + recall@k
  / MRR at the `0.85` regime; claim only "beats baseline on this set, n=…".
- **R2 — Fixture bias.** If we author the eval questions ourselves against known templates, we can
  flatter any model. Mitigation: include paraphrase/negative pairs (questions that should match *no*
  template) and report false-match rate, not just recall.
- **R3 — Dep weight / cold start.** `torch`+`sentence-transformers` inflate the image and first-load.
  Mitigation: lazy import, default-off pre-bake ARG, document the size delta honestly.
- **R4 — Staleness fix migration.** Adding `embedding_model` and changing the skip-filter must not
  break existing installs mid-upgrade (NULL rows must be safely skipped, system templates re-seed).
  Characterization test the no-opt-in path.
- **R5 — "Parked / nice-to-have."** This is a depth/polish pick; leverage is sharper offline
  retrieval, not a new capability. Scope is deliberately bounded to avoid over-investing.
- **Q1 — Ollama default string:** do we change `_default_embedding_model('ollama')` itself (a
  behaviour change for existing ollama installs → triggers reseed via the model key) or only update
  the docs recommendation? Leaning docs-only to preserve byte-stability; confirm in tech-plan.
- **Q2 — Final model pick** (bge-small vs all-MiniLM; ollama bump target): decided by the eval in the
  eval aspect.

## Out of Scope

- pgvector / a real vector store (stays JSON + Python cosine — unchanged from prior initiative).
- Changing the `0.85` threshold or the single-best-match ranking algorithm.
- Re-embedding **feedback** or any non-template content (Copilot only matches templates).
- GPU inference.
- Making the eval a CI merge gate (it is disclosure only, per M5.1).
- Lazy re-embed of org-saved templates (nice-to-have #7; skip-until-overwrite is accepted).
- `status-sync-realtime-mapping` and `feat/classifier-model-versioning-rollback` areas (in flight).
- Any plan-tier gating — all features are unlocked (MIT, self-hosted, BYOK).
