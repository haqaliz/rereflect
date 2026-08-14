# Spec — churn-classifier-core (slice 2a)

## Problem slice

The analysis-engine needs a churn-specific training/eval core: a customer-level feature
vector, a JSON-only logistic trainer, a pure-stdlib predictor, and a leakage-free A/B
against the calibrated-heuristic incumbent. Everything else (scheduling, modes, rollback)
reuses the M5.2 spine via `classifier_type='churn'`.

## In scope

- New package `services/analysis-engine/src/analyzer/churn_classifier/` mirroring the
  `corrections_classifier/` layout: `features.py`, `dataset.py`, `trainer.py`,
  `predict.py`, `evaluate.py`, `metrics.py`, `labels.py`.
- **Feature vector (fixed, documented)**, per customer at label time, reconstructible
  from existing tables: 6 health components + `health_score` + `risk_level`
  (`customer_health_history` snapshot nearest label date, else current
  `customer_health_scores`); usage (`active_days_7d/14d/30d`, `login_count_30d`,
  `usage_score`, `usage_trend_state/pct`) from the nearest `customer_usage_history`
  snapshot, else current `customer_usage`; feedback aggregates (count in window, avg
  sentiment, sentiment trend, urgency share, avg churn-risk score); `segment` slug;
  `renewal_date` proximity when CRM-enriched. Missing snapshots → documented defaults;
  the study (aspect 2) informs the final set.
- **Trainer**: TF-IDF is the wrong tool for a numeric vector — use a stdlib-serializable
  logistic regression (JSON coefficients/intercept; sklearn fit inside the function,
  lazy import; no pickle; `trainer.py` conventions).
- **Predict**: pure-stdlib reimplementation; binary sigmoid; returns calibrated
  probability + the score the incumbent would have produced, for A/B parity.
- **A/B**: reuse or byte-faithfully adapt `corrections_classifier/evaluate.py` —
  leakage-free stratified holdout (or k-fold when tiny), both sides scored on the same
  holdout, `promoted` iff `macro_f1_delta >= 0.02`; incumbent = calibrated heuristic
  (its predict over the same holdout features), identity fallback below `MIN_LABELS`
  (start 20, parity-pinned like `test_classifier_accuracy_route.py::TestMinLabelsParity`).
- **Metrics**: `compute_binary_metrics` (PR/AUC/F1/macro-F1) in the
  `corrections_classifier/metrics.py` style, hand-checked golden tests.

## Out of scope

- DB access beyond read-only feature queries (`dataset.py` fetch, mirroring
  `fetch_correction_rows`); worker task/promotion/rollback (aspect 4); predict seam
  wiring (aspect 5); settings/UI (aspect 6); the prediction-history log.
- Any change to the incumbent heuristic's own fitting.

## Acceptance criteria

1. Train → serialize → predict round-trips without sklearn at predict time
   (sklearn↔pure-stdlib parity test on training rows, `test_predict.py` convention).
2. Artifact is JSON-only; `test_no_pickle` / `test_lazy_import` equivalents green.
3. A/B is leakage-free (disjoint train/holdout tests) and `delta == 0.02` promotes
   (margin boundary test).
4. Deterministic under fixed seeds; feature builder handles all-missing-history rows
   without raising.
5. Analysis-engine suite green (`pytest tests/ -q` in `services/analysis-engine`).

## Dependencies / sequencing

- After the gate study informs the feature vector; before the worker trainer (aspect 4)
  and seam (aspect 5), which import this core lazily.

## Open questions / risks

- R3: sparse history for old labels — the feature builder's defaulting must be measured
  in aspect 2, not guessed here.
- Whether a churn-specific `evaluate.py` fork is needed vs parameterizing the existing
  one — prefer reuse; fork only if the holdout semantics differ (incumbent uses the
  same features, not text).
