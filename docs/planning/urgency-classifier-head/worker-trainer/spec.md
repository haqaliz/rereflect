# Aspect Spec — worker-trainer (worker + analysis-engine incumbent)

**Service:** `services/worker-service/src/tasks/classifier_training.py` (+ a binary incumbent helper).
**Sequence:** after urgency-core (needs `build_urgency_dataset`). Config column not strictly required for
retrain (trainer runs regardless of mode), but land data-and-config alongside to avoid churn.

## Problem slice / outcome

The weekly per-org retrain trains, evaluates, and promotes an urgency challenger against the keyword
heuristic incumbent — folded into the existing `retrain_all_orgs` loop with no new beat entry.

## In scope

- `_CLASSIFIER_TYPES` (`classifier_training.py:48`) → `("sentiment", "category", "urgency")`.
- Add an `urgency` branch to `_dataset_and_incumbent_for` (`:232-250`) returning
  `(dataset, incumbent_predict, eval_labels)`:
  - `dataset = build_urgency_dataset(org_id, db)`.
  - `incumbent_predict = _build_urgency_incumbent_predict()` — a new helper wrapping the existing keyword
    urgency heuristic (from `analyzer/core.py` / `categorizer.py`, mirrored by worker
    `tasks/analysis.py:663-708`) as a callable `text -> "urgent" | "not_urgent"`.
  - `eval_labels = URGENCY_LABELS` (fixed 2-tuple). Since vocab is closed and both incumbent and
    challenger emit both labels, the empty-intersection guard (`:295-304`) is satisfied — but confirm the
    guard passes for a fixed 2-tuple (unlike category's dynamic subset).
- Reuse unchanged: `retrain_org`, `_promote`, `_insert_eval_run`, the per-type+per-org Redis lock
  (`lock:classifier_refit:urgency:{org}` for free), `purge_old_classifier_models`, beat schedule, include.

## Out of scope

- Predict-time application of the model (predict-seam aspect).
- Mode gating in the retrain loop — the loop trains for all orgs regardless of mode (existing behavior);
  mode only governs prediction use.

## Acceptance criteria (testable, TDD)

- `retrain_all_orgs` iterates 3 types × N orgs; an urgency dataset ≥ `MIN_LABELS` with a clearly-better
  challenger → `decision="promoted"`, a row in `org_classifier_models` with `classifier_type="urgency",
  is_active=True`, and an eval-run inserted.
- A majority-class-collapse challenger (predicts all `not_urgent`) does **not** beat the keyword incumbent
  on macro-F1 → not promoted (R-3 guard). Add this test explicitly.
- Dataset below `MIN_LABELS` → `decision` reflects insufficient data, no promotion, eval-run still inserted.
- Urgency retrain for an org does not block/serialize against that org's sentiment/category retrain
  (distinct lock keys).
- The binary incumbent predictor returns exactly `"urgent"`/`"not_urgent"` and matches the current keyword
  heuristic's decision on characterization cases.

## Dependencies / sequencing

Depends on **urgency-core** (`build_urgency_dataset`, `URGENCY_LABELS`). Pairs with **data-and-config**.

## Risks

- **R-3 class imbalance** — assert macro-F1 is the promotion metric (it is, via `evaluate`); the collapse
  test is the guard.
- Incumbent fidelity: the wrapped keyword predictor must reproduce today's urgency decision so the bar is
  the real heuristic, not a strawman. Characterization-test it against `tasks/analysis.py` logic.
