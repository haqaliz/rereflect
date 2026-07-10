# PRD — Local Analyzer Sentiment Model (M5.1 spine v1)

**Slug:** `local-analyzer-sentiment-model`
**Branch:** `feat/local-analyzer-sentiment-model`
**Type:** feat (freeform, from `rereflect-next`) · **Date:** 2026-07-10
**Roadmap:** `AI-TRACKING.md:320-330` (M5.1) + `:313` (M5.0 readiness)
**Status:** Draft for review-gate approval

---

## Problem Statement

Rereflect scores sentiment with **VADER only** (`analysis-engine/src/analyzer/sentiment.py`), a
fixed lexicon that cannot improve and misreads negation, sarcasm, and domain phrasing common in
product feedback. More importantly for the roadmap: the just-planned **Local Model Layer (M5)** —
per-org self-improving classifiers (M5.2) and a per-org churn ML model (M5.3) — has **no provider
abstraction to plug into**. M5.1 is explicitly "Track B + spine v1" (`AI-TRACKING.md:320`): build
that spine for sentiment first, ship one real model behind it, and *prove* it beats the lexicon.

**Who has the problem:** self-hosting operators who want better, offline, CPU-only analysis without
sending feedback to a cloud LLM — the core OSS/self-hosted/BYOK audience. Today their only "better"
option is wiring a cloud LLM (BYOK), which many can't or won't do.

**Evidence it's real:** M5 is docs-only (commit `9592f51`); nothing is built. The heavy stack
(`torch`, `transformers`, `sentence-transformers`) is already declared in
`analysis-engine/requirements.txt:8-10` but never used — the intent exists, the spine doesn't.

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Prove the model beats the lexicon, honestly | Macro-F1 of transformer vs VADER on the labeled eval set(s) | Transformer macro-F1 **≥ VADER + 0.05** on the **in-domain** set (the claim) and **> VADER** on the public set (baseline), offline. **Floor: ≥150 labeled rows per set**; the card states `n`. |
| Zero regression for existing installs | Byte-diff of `analyze()` output with provider unset/`'vader'` | **Identical** to today (characterization-tested) |
| Works offline / air-gapped | Fresh install with `HF_HUB_OFFLINE=1` and pre-baked cache runs the transformer | No network call at runtime; documented pre-bake path |
| Spine is reusable | `resolve_sentiment_provider` mirrors `resolve_embedding_provider` shape | Same resolver/factory/base contract; M5.2 can add a `'per_org'` provider without touching call sites |
| Operators can self-assess readiness (M5.0) | AI training-readiness report returns per-org counts | Endpoint returns feedback volume + `AICorrection` counts by type + churn-label counts |

**Non-goal metric:** we do NOT claim an absolute accuracy number as marketing — only "measurably
beats VADER on a stated eval set," matching the honest brand (churn is already described as "a
calibrated heuristic").

## User Personas & Scenarios

- **Self-hosting operator (primary):** In Settings → AI, flips **Sentiment engine** from
  *VADER (default)* to *Local transformer (opt-in)*. New feedback is scored by the transformer;
  the **accuracy tab** shows the eval card (precision/recall/F1 + confusion, transformer vs VADER).
- **Air-gapped operator:** Builds the worker image with the model pre-baked; enables offline env
  flags; the transformer runs with no outbound network.
- **Operator planning M5 next steps:** Opens the **AI training readiness** report to see whether
  they have enough corrections/labels to justify M5.2/M5.3 later.

## Requirements

### Must-have
1. **Sentiment-provider abstraction** in `analysis-engine/analyzer` mirroring the embedding layer:
   an abstract `SentimentProvider` (pure, no DB), a `VaderSentimentProvider` (the current logic,
   **byte-identical default**), a `TransformerSentimentProvider`, and a small factory. The outer
   `SentimentAnalyzer` composes a provider's score with the **shared, provider-independent**
   `is_extreme` / `churn_risk` text-pattern helpers so those two fields never change.
2. **Byte-stable contract preserved.** `SentimentAnalyzer.analyze(text)` returns the same 7 keys
   in the same order (`compound, pos, neu, neg, label, is_extreme, churn_risk`); with the default
   provider the values are identical to today (characterization test locks this).
3. **Transformer provider** = `cardiffnlp/twitter-roberta-base-sentiment-latest` (3-class), CPU
   inference, lazy model load, deterministic (eval mode, no sampling). Score→contract mapping:
   softmax `[p_neg, p_neu, p_pos]` → `pos=p_pos, neu=p_neu, neg=p_neg`, `compound = p_pos − p_neg`,
   `label` via the same ±0.05 thresholds on `compound` (so label semantics match VADER's).
4. **Per-org opt-in.** New nullable column `OrgAIConfig.sentiment_provider` (default `'vader'`).
   Backend `resolve_sentiment_provider(org_id, db) -> ResolvedSentiment | None` mirrors
   `resolve_embedding_provider` (returns `None`/default on any failure, never raises). The **worker**
   (`analysis.py:479`) and the **backend synchronous create path** (`feedback.py:47`) both resolve
   and inject the provider; unset/unknown → VADER.
5. **Model packaging + air-gap.** Add `torch` + `transformers` to `worker-service/requirements.txt`
   (and `backend-api/requirements.txt` for the sync path). Wire `HF_HOME` into the worker (and
   backend) Dockerfile; add a **build-time pre-bake** step mirroring the existing NLTK download
   (`worker-service/Dockerfile:17-18`); document `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` +
   the pre-bake path in `docs/SELF_HOSTING.md`.
6. **Eval harness (offline, reproducible).** A script that runs each provider over a labeled set and
   computes precision/recall/F1/confusion per class + macro, reusing the metric pattern in
   `admin_backtest.py:56`. Ships **two** labeled sets: a small committed **public 3-class** set
   (CI baseline) and a small **hand-labeled in-domain** set derived from `sample_feedback_diverse.csv`.
7. **Accuracy card.** Backend endpoint + frontend card under the existing AI Settings `accuracy` tab
   (`settings/ai/page.tsx:41`), mirroring the churn accuracy card
   (`churn_accuracy.py:107` + `ModelAccuracyCard.tsx`): shows transformer-vs-VADER metrics on the
   eval set(s).
8. **M5.0 AI training-readiness report.** A no-ML backend endpoint returning, per org: feedback
   volume, `AICorrection` counts by type (sentiment/category/urgency), and churn-label counts +
   distribution. Surfaced as a small admin panel/card. Defines the activation thresholds M5.2/M5.3
   will later gate on.
9. **Runtime fallback + single load (no dropped work).** If the transformer provider fails to load
   or score an item, it **falls back to VADER for that item and logs** — the analysis task never
   errors (mirrors the `resolve_* → None → default` pattern). The model loads **once per worker
   process** via a lazy singleton (not per task); first-request latency is documented.
10. **Definition of done — docs/tracking.** Update `AI-TRACKING.md` (mark M5.1 shipped + note the
    M5.0 report), `docs/SELF_HOSTING.md` (pre-bake + offline flags), and the `README` capability
    row. Prevents the "tracking lags reality" drift.

### Should-have
- Settings validation: selecting `'transformer'` while the model isn't importable/available returns
  an honest error (mirror the `LOCAL_PROVIDERS`-need-`base_url` validation in `ai_settings.py:412`).
- A `GET /settings/ai/sentiment/status` endpoint (mirror `/embeddings/status`, never raises) so the
  UI can show configured/available/model without guessing.
- Provider/label tagging on persisted eval runs (mirror `embedding_provider`/`embedding_dimension`
  tagging) so results record which provider produced them.

### Nice-to-have (explicitly deferrable)
- Optional **emotion** head (roadmap says "+ optional emotion") — defer unless cheap.
- Batch/vectorized transformer inference for throughput.
- Caching the loaded model across worker tasks (process-level singleton) beyond a simple lazy global.

## Technical Considerations

- **Services changed:** `analysis-engine` (provider layer), `worker-service` (deps, Dockerfile,
  injection at `analysis.py:479`), `backend-api` (`OrgAIConfig` column + migration, resolver,
  ai-settings schema/route, status + accuracy + readiness endpoints, injection at `feedback.py:47`,
  deps), `frontend-web` (settings toggle + accuracy card + readiness panel).
- **The DB-access split** is the central design constraint: the provider abstraction stays **pure**
  in `analysis-engine` (no DB import); per-org resolution happens **backend-side** and the resolved
  provider instance is injected into the analyzer at the two call sites. This keeps analysis-engine
  importable-as-copied-source (`worker-service/Dockerfile:25`) with no new coupling.
- **Multi-tenancy:** all new endpoints scope by `organization_id` from JWT; `sentiment_provider` is
  per-org on `OrgAIConfig` (already unique per org).
- **Migration:** one Alembic migration adds `sentiment_provider` (nullable, default `'vader'`).
  Repo has a known **multi-heads** condition (memory: `rereflect-repo-test-gotchas`) — resolve
  `alembic heads`/`merge` before adding.
- **Determinism:** transformer in `eval()`, no dropout/sampling, pinned model revision; keep VADER
  path untouched. Byte-stability guarded by a characterization test.
- **Image size:** worker/backend images grow (~torch + ~500MB weights if baked). Acceptable and
  documented; the model is **opt-in** so the default image can optionally skip the pre-bake and
  only pull on first enable (with the offline pre-bake path documented for air-gap).

### Data Model
```
OrgAIConfig (existing table org_ai_config)
  + sentiment_provider  VARCHAR  NULL  DEFAULT 'vader'   # 'vader' | 'transformer'
```
No new table required for slice 1 (eval runs may be persisted later; the card can compute on demand
from the committed eval sets + live provider, mirroring how the churn card summarizes runs).

### API Contracts (FastAPI, prefix `/api/v1/settings/ai` unless noted)
- `PATCH /` — extend `AISettingsUpdate`/`AISettingsResponse` with `sentiment_provider`
  (`model_fields_set` pattern; validate against `{'vader','transformer'}`).
- `GET /sentiment/status` — `{ provider, available, model }`, never raises.
- `GET /sentiment/accuracy` — transformer-vs-VADER metrics on the eval set(s) for the card.
- `GET /analytics/ai-readiness` (or under settings) — M5.0 per-org counts.

### Non-Functional
- CPU-only; no GPU ever required. Offline-capable. Default install byte-identical.

## Risks & Open Questions
- **Out-of-domain eval risk:** the public set may not reflect product feedback → mitigated by also
  shipping the hand-labeled in-domain set (the honest claim rests on the in-domain result).
- **Image bloat / air-gap:** biggest adoption risk → mitigated by opt-in + documented pre-bake +
  offline env flags. Open: bake weights into the image by default, or pull-on-first-enable? (Lean:
  don't bake by default to keep the base image lean; document both.)
- **Two call sites diverging:** both must resolve the same provider; covered by must-have #4.
- **Label mapping fidelity:** `compound = p_pos − p_neg` is a defensible mapping but not VADER's;
  the eval card is exactly what validates the mapping is an improvement, not just different.
- **Model licensing/provenance:** confirm the HF model + any bundled public eval set have
  redistribution-compatible licenses before committing data to the MIT repo.
- **Cold-start latency / OOM on small boxes:** ~500MB model load inside a Celery task on a modest
  self-host node → mitigated by the per-process lazy singleton (must-have #9) and opt-in default;
  document the first-request latency + minimum RAM in `SELF_HOSTING.md`.
- **RESOLVED (eval = disclosure, not gate — decided at review gate 2026-07-10):** the eval is a
  **disclosure**, not a merge gate. Ship the spine + transformer provider **even if it loses
  in-domain**, kept **OFF by default**, with the accuracy card stating the honest result (incl. `n`).
  The spine — the real M5.1 goal — lands regardless, unblocking M5.2/M5.3. The +0.05/n≥150 success
  target is what the card *reports against*, not a condition for merging. Merge criteria = spine
  works + default byte-stable + card is honest.

## Out of Scope
- Category/urgency model backends (later M5) — sentiment only this slice.
- **Per-org training** (M5.2) and **churn ML** (M5.3) — spine only; M5.0 report ships to inform them.
- Fine-tuning the transformer, multilingual support, streaming/batch inference optimization.
- Changing the stored `feedback` schema beyond what already exists.
