# Aspect Spec — training-and-eval-core

**Parent PRD:** `../prd.md` (M5.2 per-org-corrections-classifier)
**Sequence:** after `data-layer`; parallel with `predict-seam-resolver`.

## Problem slice / outcome

The pure-compute brain: build a labeled dataset from an org's sentiment corrections, train a
CPU-only TF-IDF + logistic-regression classifier into a **JSON** artifact, and run the shadow-A/B
that decides promote-vs-retain. No Celery, no HTTP, no DB writes — deterministic functions given
inputs, mirroring how `churn_calibrator.py` is pure compute driven by `calibration_refit.py`.

## In-scope

1. **Dataset builder** `build_sentiment_dataset(org_id, db) -> list[(text, label)]`:
   - Query `ai_corrections` for `organization_id`, `correction_type='sentiment'`, `signal='correction'`,
     `corrected_value IS NOT NULL`.
   - Text = `feedback_text` if present else join `FeedbackItem.text` on `entity_id` (same org); drop rows
     with no resolvable text. Label = `corrected_value` in `{positive, neutral, negative}` (drop
     out-of-vocab labels).
2. **Trainer** `train_classifier(dataset) -> artifact_json`: `TfidfVectorizer` + `LogisticRegression`
   (scikit-learn, **lazy import inside the fn**). Serialize to JSON: vocabulary + idf weights + logreg
   `coef_`/`intercept_` + `classes_` (+ vectorizer params). **No pickle.** Deterministic (fixed
   `random_state`, sorted vocab).
3. **Predict-from-artifact** `predict(artifact_json, text) -> (label, proba_dict)` — pure, reconstructs
   the linear model from JSON, no sklearn model object required at predict time (or a lazy rebuild);
   used by aspect D too, so expose it cleanly.
4. **sentiment_score map** `score_from_proba(proba) -> float` = `clamp(P(positive) − P(negative), -1, 1)`
   (per PRD; exact formula confirmed here).
5. **Shadow-A/B** `evaluate(dataset, incumbent_predict, challenger_artifact, *, min_labels, holdout_frac,
   min_holdout, margin) -> EvalResult`:
   - Gate: `len(dataset) >= min_labels` else `decision='skipped'`.
   - Held-out split (stratified; k-fold when tiny). **Small-sample guard:** held-out ≥ `min_holdout`
     AND all 3 classes present, else `decision='retained'` (`notes='held-out too small'`).
   - Score incumbent + challenger over the held-out set; two confusion matrices; reuse
     `scripts/eval_sentiment.py::compute_multiclass_metrics`. `macro_f1_delta = challenger − incumbent`.
   - `decision='promoted'` iff `delta >= margin`, else `'retained'`. Return incumbent/challenger macro-F1,
     delta, decision, n, notes.
   - **Disclosure, never a build gate** (mirror eval_sentiment always-exit-0 ethos).

## Out-of-scope

- Reading/writing model rows or the `is_active` flip (aspect C). The mode flag / call-site injection
  (aspect D). Scheduling (aspect C).

## Acceptance criteria (testable)

- Builder: synthetic `ai_corrections` (some with `feedback_text`, some needing the `FeedbackItem` join,
  some undroppable) → correct `(text,label)` set; out-of-vocab labels and text-less rows dropped.
- Trainer: round-trips through JSON and `predict()` reproduces sklearn's own predictions on the training
  rows; artifact contains no pickled bytes (assert JSON-serializable + no `\x80` markers).
- `score_from_proba`: `P(pos)=1 → 1.0`, `P(neg)=1 → -1.0`, uniform → ~0; always in [-1, 1].
- Evaluate: below `min_labels` → skipped; tiny/one-class held-out → retained with the guard note;
  clearly-better challenger → promoted with positive delta; worse challenger → retained.
- Every sklearn/numpy import is inside a function (no module-level heavy import) — assert importability
  without sklearn installed (mirror the churn calibrator test).

## Dependencies & sequencing

- **Blocked by:** data-layer (artifact shape / AICorrection worker mirror if this lives worker-side).
  **Blocks:** worker-trainer-and-schedule, predict-seam-resolver (they call these fns).
- Home: a pure module mirroring the churn split — recommend `analysis-engine` or a backend `services/`
  module importable by both worker + backend (confirm in tech-plan).

## Open questions / risks

- Incumbent-predict function for the A/B: inject a callable that live-scores via `SentimentAnalyzer`
  (recommended, fair) — keep `evaluate` agnostic by taking `incumbent_predict` as a param.
- Lock `min_labels=20`, `holdout_frac=0.2–0.25`, `min_holdout≈8`, `margin=+0.02` (tech-plan).
