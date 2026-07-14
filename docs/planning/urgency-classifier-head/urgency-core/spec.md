# Aspect Spec — urgency-core (analysis-engine)

**Service:** `services/analysis-engine/src/analyzer/corrections_classifier/`
**Sequence:** 1st — foundation; worker-trainer depends on it. No dependencies.

## Problem slice / outcome

Give the generic classifier spine a binary "urgency" vocabulary and dataset builder, so a per-org urgency
model can be trained/evaluated by the exact same primitives that serve sentiment and category.

## In scope

- `labels.py`: add `URGENCY_LABELS: tuple[str, ...] = ("not_urgent", "urgent")` (sorted lexicographically →
  `classes[0]="not_urgent"`, `classes[1]="urgent"` = positive class for the binary sigmoid path).
- `dataset.py`: add
  `build_urgency_dataset(org_id, db) -> rows_to_dataset(fetch_correction_rows(org_id, db, correction_type="urgency"), allowed_labels=URGENCY_LABELS)`.
  (No `fetch_urgency_correction_rows` alias — category didn't add one; keep parity.)
- `__init__.py`: export `URGENCY_LABELS` and `build_urgency_dataset`.

## Out of scope

- Any edit to `trainer.py`, `predict.py`, `evaluate.py`, `metrics.py` — all already type-generic; the
  binary sigmoid path in `predict()` (`len(coef)==1`) already exists. **Do not touch them.**
- `score_from_proba` (sentiment-only `"positive"/"negative"` keys) — urgency bypasses it, like category.

## Acceptance criteria (testable, TDD)

- `URGENCY_LABELS == ("not_urgent", "urgent")` and is exported.
- `build_urgency_dataset` calls `fetch_correction_rows` with `correction_type="urgency"` and filters to
  `URGENCY_LABELS` (junk `corrected_value`s dropped), returning `list[(text, label)]`.
- `rows_to_dataset(rows, allowed_labels=URGENCY_LABELS)` drops rows whose label ∉ URGENCY_LABELS and rows
  with no resolvable text (feedback_text fallback to joined_text).
- `train_classifier(dataset, classifier_type="urgency")` produces an artifact with
  `classifier_type="urgency"`, `classes` reflecting present labels, and a `(1, n)` coef for 2 classes
  (asserted via existing trainer test patterns).
- `evaluate(dataset, incumbent_predict, train_classifier, labels=URGENCY_LABELS)` returns a valid
  `EvalResult` for a 2-class dataset.

## Dependencies / sequencing

None. Must land before worker-trainer.

## Risks

- Ensure `URGENCY_LABELS` ordering is lexicographic so the positive class ("urgent") is `classes[1]` —
  matches `predict()`'s binary branch semantics. Add an explicit test asserting the order.
