# Understanding — feat/local-analyzer-sentiment-model (Phase 2 dig)

**Date:** 2026-07-10 · **Slug:** local-analyzer-sentiment-model
_(Overwrites a stale `understanding.md` inherited from the prior `segment-actions` task.)_

## What the task is really asking (M5.1, `AI-TRACKING.md:320-330`)
Introduce a **pluggable sentiment-provider layer** where **VADER stays the byte-stable
default** and a **CPU transformer model is an opt-in provider**, plus an **eval harness +
accuracy card** that proves the model beats VADER on a labeled set — offline, no default
behavior change. This is the "spine v1" the rest of M5 (per-org classifiers M5.2, churn ML
M5.3) plugs into.

## Affected services / areas
- **analysis-engine** (`src/analyzer/`) — the pure sentiment implementation (VADER today).
- **worker-service** (`src/tasks/analysis.py`) — the primary runtime that actually executes
  sentiment; **this is where deps + provider selection really land.**
- **backend-api** — per-org AI config (`OrgAIConfig`), AI-settings route, a status/accuracy
  endpoint, and a **2nd synchronous sentiment call site** (`feedback.py:47`).
- **frontend-web** — AI Settings page (`settings/ai/page.tsx`) opt-in toggle + accuracy card.

---

## Key facts (grounded, file:line)

### 1. The sentiment core & byte-stable contract
- `analysis-engine/src/analyzer/sentiment.py:29` — `SentimentAnalyzer.analyze(text) -> Dict[str,float]`
  returns **7 keys in order**: `compound, pos, neu, neg, label, is_extreme, churn_risk`.
  VADER floats are **not rounded** at this layer; rounding happens downstream in `core.py`.
- Label thresholds (inclusive ±0.05): `compound>=0.05`→positive, `<=-0.05`→negative, else neutral
  (`sentiment.py:41-47`). `is_extreme`/`churn_risk` are **text-pattern based → provider-independent**.
- **Stored value** (what actually persists) = `feedback.sentiment_label` (String) +
  `sentiment_score` (Float) on `backend-api/src/models/feedback.py:19-20`. The full aggregated
  `AnalysisResult` (with 2–3 decimal rounding) is a separate analysis-engine API path.
- VADER is **fully deterministic** (no seeds/model load). Byte-stability = a new provider,
  when NOT selected, must leave `analyze()` output identical; when selected, it changes
  `compound`/`label` (expected).

### 2. Provider pattern to mirror (already in the repo)
- **Embedding layer** `backend-api/src/services/embeddings/`: `base.py` (ABC) → `factory.py`
  (`create(provider, *, api_key, base_url, model)`, lazy per-branch imports) → `resolver.py`
  `resolve_embedding_provider(org_id, db) -> Optional[ResolvedEmbedder]` (**returns None on any
  failure, never raises**). Providers are NOT self-registering — the factory `if/elif` is the registry.
- **LLM layer** `copilot/llm_resolver.py`: `resolve_generation_llm(org_id, db) -> LLMConfig`
  with an **`is_configured` gate** (returns a config always, pushes the unconfigured decision to
  the caller). `_LOCAL_PROVIDERS = {"ollama","openai_compatible"}` keyless branch.
- **Per-org config** lives in **one table `OrgAIConfig`** (`models/org_ai_config.py`): existing
  precedent columns `default_provider`, `base_url`, `model_embeddings` (nullable, read via
  `getattr(...)`), and **opt-in-defaulted** `health_weight_usage`/`crm` (default 0). → a new
  **`sentiment_provider` column (default `'vader'`)** belongs here.
- AI-settings route `ai_settings.py` (prefix `/api/v1/settings/ai`): schemas `AISettingsResponse`
  (`:55`) + `AISettingsUpdate` (`:63`), `PATCH` uses `model_fields_set` to distinguish
  explicit-null from omitted. Status-endpoint precedent: `GET /embeddings/status` (`:819`) never raises.

### 3. Per-org CPU model precedent (`churn_calibrator.py`)
Per-org sklearn model → **serialize fitted arrays (not pickled estimator), enforce min-data
threshold with deterministic global fallback, pin RNG seeds, keep fit/predict pure/no-I/O.**
Good for M5.2's per-org fit later; does **not** cover downloading large transformer weights
(no such precedent exists — only BERTopic, lazy-imported + not persisted).

### 4. Packaging / model caching (the real air-gap gap)
- torch/transformers/sentence-transformers are declared **ONLY** in
  `analysis-engine/requirements.txt:8-10`. **NOT in worker-service or backend-api.**
- The worker **copies** `analysis-engine/src/analyzer` into its image
  (`worker-service/Dockerfile:25`, `PYTHONPATH=/app`) and does **not** pip-install analysis-engine
  deps. Since sentiment executes in the worker (and backend sync path), a transformer provider
  **must add torch+transformers (or sentence-transformers) to `worker-service/requirements.txt`**
  (and backend-api if the sync path can run it).
- `HF_HOME`/`TRANSFORMERS_CACHE` set only in `analysis-engine/.env:15-16`; **not wired into any
  Dockerfile/compose.** No `from_pretrained`/`SentenceTransformer(...)` call exists anywhere yet.
- **Pre-bake precedent exists**: `worker-service/Dockerfile:17-18` already does build-time
  `nltk.download('vader_lexicon', ...)`. Mirror it: build-time `from_pretrained`/`snapshot_download`
  into a baked `HF_HOME=/app/models`, + `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` for air-gap.

### 5. Eval harness + accuracy card precedents
- Metrics: `admin_backtest.py:56` `_safe_precision_recall_f1_accuracy(tp,fp,fn,tn)` +
  `_compute_backtest_metrics`. Script precedent: `backend-api/scripts/backtest_churn.py`
  (`is_churned`, `compute_metrics`), tests `tests/test_backtest_backfill_scripts.py`.
- Accuracy card: backend `churn_accuracy.py:107` `get_org_accuracy_card`; frontend
  `components/dashboard/widgets/ModelAccuracyCard.tsx` + `AccuracyTrendChart.tsx`.
- The AI Settings page **already has an `accuracy` tab** (`settings/ai/page.tsx:41`
  `VALID_TABS=[...,'accuracy']`) → the eval accuracy card renders there.
- Labeled data: repo has `sample_feedback_diverse.csv` at root (needs sentiment labels).

---

## Contradictions / risks to flag (surface, don't paper over)
1. **DB-access split (architecture tension).** The provider abstraction naturally lives in the
   pure `analysis-engine/analyzer` package (no DB), but the per-org opt-in (`OrgAIConfig`) is a
   backend DB read. The two sentiment call sites (worker `analysis.py:479`, backend
   `feedback.py:47`) DO have `db`/`org` in scope. **Resolution options for the PRD:** (a) a
   global env `SENTIMENT_PROVIDER` toggle read in the analyzer (simplest, mirrors
   `main.py:30-32`) — but that's not per-org and diverges from the embedding/LLM layers; (b) a
   backend-side `resolve_sentiment_provider(org_id, db)` that instantiates the provider and the
   call sites inject it into the analyzer — per-org, consistent with the spine, more wiring.
   **Recommend (b)** for spine fidelity; confirm in interview.
2. **Deps land in worker-service, not analysis-engine** — the "already installed" note in the
   handoff (`AI-TRACKING.md:304`) is true for analysis-engine but the runtime that matters
   (worker) does NOT have them. Real work: add heavy deps to worker (image size ↑).
3. **No labeled eval set** — must source/build one (public 3-class sentiment corpus, or
   hand-label a sample of `sample_feedback_diverse.csv`). "Beats VADER" is meaningless without it.
4. **3-class match** — VADER is 3-class (pos/neu/neg). A binary SST-2 model would be a poor drop-in;
   a 3-class model (e.g. `cardiffnlp/twitter-roberta-base-sentiment-latest`) maps cleanly. Confirm
   model choice + how its scores map to the `compound`-shaped contract in the interview.
5. **Two call sites must stay consistent** — worker (async) and backend `feedback.py:47`
   (synchronous create). Both need the provider or the sync path stays VADER-only (acceptable if scoped).

## Open questions for the requirements interview (Phase 3)
- Opt-in granularity: **per-org `OrgAIConfig` column** (spine-consistent) vs global env toggle?
- Where the provider abstraction physically lives given the DB-access split (recommend backend
  resolver + injectable provider into the pure analyzer).
- Model choice (3-class transformer; emotion optional) + score→contract mapping.
- Labeled eval-set source (public corpus vs hand-labeled internal sample) + where it's stored.
- Does slice 1 cover both call sites, or worker-only first?
- Include the cheap **M5.0 readiness report** (`AI-TRACKING.md:313`) in this slice or defer?
