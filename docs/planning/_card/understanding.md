# Understanding — feat/per-org-corrections-classifier (M5.2)

Synthesis of the Phase 2 deep dig (4 parallel code-mapping agents). All paths relative to the
worktree base. This is the input to the Phase 3 `prd-interview`.

## What the task is really asking

Close the **corrections flywheel**: train a **small, per-org, CPU-only** text classifier on the
org's own feedback + `AICorrection`s, run it in **shadow** against the incumbent analyzer, and
**auto-promote it only when it measurably beats the incumbent** on held-out corrections — with an
operator-visible delta and one-click rollback. Mirror the proven M5.1 provider-seam + M4.1
churn-calibrator per-org-fit patterns. Honest framing: "your model, trained on your data,
promoted only when measurably better."

## The four platform pieces this builds on (all present)

1. **M5.1 provider seam** (`analysis-engine/src/analyzer/sentiment_providers/`): `SentimentProvider`
   ABC (`score()`), factory, lazy/singleton loading, `SentimentAnalyzer(provider=...)` injection.
   Per-org resolution via `resolve_sentiment_provider(org_id, db)` — **duplicated in both**
   backend-api and worker-service — reading `OrgAIConfig.sentiment_provider`; returns `None`→VADER,
   never raises. Two call-sites inject it: worker `tasks/analysis.py` (`_apply_keyword_analysis`,
   ~L508) and backend inline `routes/feedback.py` (~L92).
2. **M4.1 churn-calibrator per-org fit** (`services/churn_calibrator.py` + worker
   `services/calibration_refit.py`): the storage/versioning/schedule template — **JSON artifact in a
   versioned row** (`churn_calibration_models`, `model_json` JSON, **not pickle**), `is_active`
   partial-unique (one active per org), `MIN_LABELS=20` gate, insert-new+flip-old versioning,
   three-tier load fallback (`org active → global active → identity`), 90-day purge. Weekly celery
   beat refit (`tasks/churn_calibration.py`, Mondays 07:45 UTC).
3. **M5.1 eval harness** (`scripts/eval_sentiment.py`): `compute_multiclass_metrics(confusion,labels)`
   (per-class + macro P/R/F1, degenerate-safe) and `run_provider(provider, rows, name)` —
   **provider-injected, `None`-challenger short-circuits**. This is the exact shape for M5.2's
   shadow-A/B shootout (two confusion matrices, diff `macro_f1`, `macro_f1_delta` + `meets_target`).
   Disclosure-only, never a CI gate — mirror that (metric decides promote, never fails a build).
4. **M5.0 readiness gate** (`routes/ai_readiness.py`, `config/readiness_thresholds.py`):
   `GET /api/v1/analytics/ai-readiness` returns `corrections_by_type`, `correction_volume_target`
   (=200), `correction_volume_ready`. Decides per-org activation.

## Training data reality (AICorrection)

- Table `ai_corrections` (`models/ai_correction.py`), index `ix_ai_corrections_org_type`. Fields:
  `correction_type`, `entity_type`, `entity_id`, `signal` (thumbs_up/down/correction),
  `original_value`, `corrected_value`, `feedback_text`.
- **Only `sentiment` and `category` correction types are usable training labels.** `churn_risk` is a
  thumbs-down on a numeric health score (no class label); `copilot_response` is a thumbs rating on
  free text; no `urgency` correction type exists in code.
- **`category` collapses pain-point + feature-request** into one `correction_type='category'` — must
  disambiguate via `original_value` matching the 12-cat pain-point vs 10-cat feature-request domains,
  and train two heads.
- **Text join gotcha**: internal frontend corrections do **not** populate `feedback_text`; only the
  public-API PATCH does. So the trainer must join `FeedbackItem.text` via `entity_id` to get input
  text. Use `AICorrection.original_value` for the old label (point-in-time; the live `FeedbackItem`
  column may have drifted since — corrections are record-only).
- **Gate gotcha**: `correction_volume_ready` is a **grand-total** proxy (≥200), not per-type — it can
  go green with 200 `copilot_response` corrections and **zero usable labels**. M5.2 must read
  `corrections_by_type["sentiment"|"category"]` itself and apply its own per-type threshold.

## Featurization decision (net-new — must resolve in interview)

- **There is NO `sentence-transformers` in the repo.** "Local embeddings" are HTTP calls to an
  OpenAI-compatible endpoint (Ollama/LM Studio), not in-process. So M5.2's "logreg-on-embeddings via
  sentence-transformers" is a **net-new dependency decision**.
- **scikit-learn IS installed** and used (lazily) by the churn calibrator. **TF-IDF + logistic
  regression on scikit-learn** is the CPU-cheap, keyless, no-new-heavy-dep option — small JSON
  artifact (vocab + coefficients), no torch, no HTTP. Strong default recommendation.
- Alternative: reuse the existing HTTP embedding provider (`services/embeddings/`) for
  logreg-on-embeddings — but that reintroduces a network/BYOK dependency, against the fully-offline
  goal. **Recommend TF-IDF+logreg for v1**; embeddings as a later variant.

## The shadow/promoted seam

- Best single seam: worker `tasks/analysis.py::_analyze_feedback_item` (~L420), **after**
  `_apply_llm_result`/`_apply_keyword_analysis` set the incumbent, **before** `db.commit()`.
- **Mode flag on `OrgAIConfig`** (e.g. `classifier_mode ∈ {off, shadow, promoted}` per task):
  - shadow → compute challenger prediction, log to a side table, do NOT touch `feedback.*`.
  - promoted → overwrite the specific `feedback.<field>` before commit.
- Resolver `resolve_classifier(org_id, task_type, db)` mirrors `resolve_sentiment_provider`,
  **duplicated in both services**, `getattr`-defensive, never raises.

## First-target decision (the main open question)

Two agents diverge on the cleanest first target:
- **Sentiment-first** (agent D): fixed 3-class vocabulary (positive/neutral/negative), **no per-org
  taxonomy reconciliation**, and it can slot in as a third `SentimentProvider` — reuses the M5.1
  seam almost verbatim. But sentiment corrections may be sparse, and sentiment is already decent.
- **Category-first** (agent B): category corrections are likely more frequent and where per-org
  taxonomies actually differ (the real moat), but needs vocabulary reconciliation (built-ins ∪
  active `CustomCategory`) and pain/feature disambiguation.
- **Recommendation to pressure-test in the interview:** build the **task-agnostic training +
  shadow-A/B + promote/rollback spine once**, and land **sentiment as the first task** (cleanest,
  proves the machinery end-to-end with synthetic corrections), with **category as the immediate
  follow-on** once the spine is proven. Label vocabulary per task = fixed (sentiment) or built-ins ∪
  custom (category).

## Recommended M5.2 shape (mirrors existing conventions)

- **New table `org_classifier_models`** (mirror `churn_calibration_models`): `organization_id`
  (nullable = global/base), `classifier_type` (sentiment/pain_point/feature_request), `model_json`
  (vectorizer vocab + logreg coeffs + classes — **no pickle**), `label_count`, denormalized
  `macro_f1/precision/recall/accuracy` (Numeric(5,4)), `fit_at`, `is_active`; partial-unique **one
  active per (org, classifier_type)**. Optional `org_classifier_eval_runs` = `churn_backtest_runs`
  analog for shadow-A/B history. Purge inactive >90 days.
- **Gate**: per-type `MIN_LABELS` (reuse the 20-label semantics; own per-type threshold, not the
  M5.0 grand-total flag). Below gate → skip, serve base/incumbent.
- **Schedule**: worker `tasks/classifier_training.py::retrain_all_orgs`, added to `celery_app.py`
  `include=[...]` + a `beat_schedule` entry in an **uncrowded Monday slot** (e.g. 06:30 UTC), per-org
  `try/except` like `refit_all_orgs`.
- **Predict/shadow**: resolver + mode flag + side-table logging; three-tier fallback; corrupt-artifact
  → incumbent.
- **API/UI**: `ai_settings.py` mode toggle + a per-org accuracy/delta card (reuse the churn-accuracy
  card pattern) showing challenger-vs-incumbent macro-F1 and last-N runs; deps-availability gate like
  `_sentiment_transformer_deps_available()` if any heavy path is chosen.

## Cross-cutting gotchas (carry into plan)

1. **Both-service model/resolver mirroring** — `OrgAIConfig`, resolvers, and any new model exist
   **twice** (backend-api + worker-service `models/__init__.py`); **`AICorrection` is NOT yet mirrored
   in the worker** — must add it so the trainer can read corrections.
2. **Alembic**: currently a **single head** (`6ad1dc4335f1_add_sentiment_provider`). Set
   `down_revision='6ad1dc4335f1'`; run `alembic heads` before generating; add a merge migration only
   if a concurrent branch reintroduces multiple heads.
3. **CPU-only + lazy imports** — no top-level sklearn/numpy import (Py3.14 CI venv lacks wheels); no
   torch/GPU; keep artifacts small JSON, never pickle.
4. **Byte-stable default** — off by default; shadow never mutates stored values; promotion opt-in +
   reversible.
5. **Analyzer cache keyed by provider-name only** — per-org weights need an **org-scoped cache key**.
6. **Two call-sites** (worker + backend inline) — put shared predict/log/resolve in a service used by
   both, or let the worker own promotion.

## Scope boundary (honest, from the card caveat)

First slice = build + prove the **spine** (train → shadow-A/B → promote-only-if-better → rollback)
end-to-end on **seeded/synthetic corrections**, for **one task-type (sentiment)**. "Promoted on a
real design-partner org's held-out data" is the later exit, not the first PR. Category is the
immediate follow-on. M5.3 (churn ML) and M5.4 (embeddings) remain out of scope.
