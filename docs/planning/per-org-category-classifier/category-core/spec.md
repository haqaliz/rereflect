# Aspect: category-core (analysis-engine spine)

**Slice:** make the `corrections_classifier` spine task-generic and add the category dataset + label vocab.

## Problem slice & outcome
The spine is ~90% generic; only four sentiment touch-points block a category head. Parameterize them
(sentiment default preserved, byte-stable) and add a category dataset builder with a **dynamic** label
set derived from the org's own corrections.

## In scope (all under `services/analysis-engine/src/analyzer/corrections_classifier/`)
- `dataset.py`:
  - `rows_to_dataset(rows, allowed_labels=SENTIMENT_LABELS)` — parameterize the label filter (`:45`).
    For category, `allowed_labels=None` ⇒ accept all non-empty `corrected_value`s (dynamic vocab).
  - `fetch_correction_rows(org_id, db, *, correction_type)` — parameterize `:71`; keep
    `fetch_sentiment_correction_rows` as a thin alias.
  - `build_category_dataset(org_id, db)` querying `correction_type='category'`; keep
    `build_sentiment_dataset` alias.
  - Helper `derive_labels(dataset) -> tuple[str,...]` = sorted unique labels present (for evaluate()).
- `trainer.py`: thread `classifier_type` through `train_classifier(...)` → `_serialize` (replace hard-coded
  `_CLASSIFIER_TYPE="sentiment"` at `:64`).
- `evaluate.py`: add `labels: tuple[str,...] = SENTIMENT_LABELS` param to `evaluate()`; replace `:205`.
  All downstream helpers already take `labels`. For category, caller passes the label set to score on.
  **Fair-A/B constraint (resolves critique #3):** the category caller passes `labels = derive_labels(dataset)
  ∩ built_in_category_vocab` — i.e. score only over labels the keyword incumbent can actually emit, so the
  challenger is not credited for classes the baseline could never guess. `derive_labels` returns the full
  set; the intersection happens at the call boundary (documented so the accuracy card can say "evaluated on
  labels the baseline can produce").
- `labels.py`: keep `SENTIMENT_LABELS`; knobs unchanged (already generic). (No fixed category tuple —
  category vocab is dynamic.)
- `predict.py`: **no change** to `predict()`; `score_from_proba` stays sentiment-only (caller bypasses it
  for category — documented in predict-seam).
- `__init__.py`: export the new generic names.

## Out of scope
- Worker orchestration, incumbent construction, DB writes (→ worker-trainer). Seam/override (→ predict-seam).

## Acceptance criteria (testable)
- Sentiment path byte-identical: existing `corrections_classifier` tests pass unchanged; a
  characterization test asserts `build_sentiment_dataset` + `evaluate(dataset, ...)` produce identical
  `EvalResult` to before.
- `build_category_dataset` returns `[(text,label)]` for `correction_type='category'` rows, same-org text
  join, dynamic labels (custom category names survive).
- `evaluate(dataset, incumbent, train_fn, labels=<eval-label-set>)` runs on a ≥2-class category
  dataset and returns a valid `promoted|retained|skipped` decision; open label set (a class absent from
  holdout) yields `retained "held-out missing class"` rather than crashing.
- Fair-A/B: a dataset whose labels include a custom category **not** in the built-in vocab is evaluated
  only over the built-in∩derived subset (the challenger gets no free credit for the custom-only class) —
  add a test asserting the label set passed to `evaluate` excludes the incumbent-impossible class.
- `train_classifier(dataset, classifier_type='category')` writes `classifier_type='category'` into the
  artifact; `classes` reflect the dynamic labels.

## Dependencies & sequencing
Independent of data-and-config (pure engine). **Blocks:** worker-trainer, predict-seam. Can build in
parallel with data-and-config.

## Open questions / risks
- Open/dynamic label set stresses the stratified split guards — add tests for a rare class (n=1) and a
  single-class dataset (→ skipped/retained, never raises).
