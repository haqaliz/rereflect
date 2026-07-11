# Aspect: worker-trainer

**Slice:** train + promote a per-org category model on the worker, alongside sentiment, on schedule.

## Problem slice & outcome
Extend `retrain_all_orgs` to run both classifier types. The promote/eval/lock/purge machinery is already
type-agnostic once `_CLASSIFIER_TYPE` is a parameter; add a category incumbent and the category dataset
wiring.

## In scope (`services/worker-service/src/tasks/classifier_training.py`)
- Parameterize `_CLASSIFIER_TYPE` → an argument threaded through `retrain_org`, `_promote`,
  `_insert_eval_run` (currently `:45,98,150`).
- `retrain_all_orgs`: loop `for classifier_type in ("sentiment","category"): for org_id in ...`. Keep the
  shared-session rollback-on-error discipline (`:263-268`) per (type, org).
- **Per-type Redis lock key:** `lock:classifier_refit:{classifier_type}:{org_id}` (`:187`) so the two
  heads run independently per org.
- Dataset dispatch: `build_sentiment_dataset` vs `build_category_dataset` by type (`:202`).
- **Category incumbent:** `_build_category_incumbent_predict()` wrapping the keyword categorizer
  (`analysis-engine .../analyzer/categorizer.py` PainPoint/FeatureRequest categorizers) → returns a
  `text -> label` callable whose label space matches the built-in category vocab. Dispatch incumbent by
  type beside `_build_incumbent_predict` (`:67`).
- Pass the **fair-A/B label set** into `evaluate()` for category: `derive_labels(dataset) ∩
  built_in_category_vocab` (the labels the keyword incumbent can emit), so promotion isn't rigged by
  custom-only classes the baseline can't produce (critique #3).
- Purge (`:286-309`) unchanged (not type-scoped — already covers category rows).
- Beat: keep the single `retrain-classifier-weekly` slot (`celery_app.py:186-192`); the task now loops
  both types (no new beat entry).

## Out of scope
- The mode read / seam (→ predict-seam). The engine spine edits (→ category-core). Migration (→ data-and-config).

## Acceptance criteria (testable)
- With synthetic category corrections for an org (≥ `MIN_LABELS`, ≥2 classes, a beatable incumbent),
  `retrain_org(org_id, db, classifier_type="category")` promotes a model: one `OrgClassifierModel`
  row `classifier_type='category', is_active=True` + one `OrgClassifierEvalRun decision='promoted'`.
- Atomic-promote holds: the pre-existing active category model is deactivated before the new insert
  (flush-order), never two active rows for `(org,'category')` (partial-unique index).
- Below-gate synthetic org → `skipped` eval-run, no model row.
- Sentiment retrain path unchanged (existing tests green); the two types don't share a lock.
- `retrain_all_orgs` returns tallies covering both types; purge still runs.

## Dependencies & sequencing
**Blocked by:** category-core (dataset + evaluate param), data-and-config (not strictly — training doesn't
read mode, but keep ordering). Build after category-core.

## Open questions / risks
- Category incumbent must be deterministic and cheap; ensure it imports lazily (Py3.14 CI target, mirror
  the existing lazy-import discipline `:197-200`).
