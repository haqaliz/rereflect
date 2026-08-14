# Spec — worker-churn-trainer-and-schedule (slice 2b)

## Problem slice

A scheduled per-org training task that runs the churn core's A/B, promotes on a
measurable margin, and stays reversible — following the M5.2 worker conventions exactly,
for `classifier_type='churn'`.

## In scope

- `services/worker-service/src/tasks/churn_classifier_training.py` cloning
  `classifier_training.py`: `retrain_org(org_id, db)` / `retrain_all_orgs()` with
  per-(org) try/except + rollback, Redis advisory lock
  (`lock:classifier_refit:churn:{org_id}`), `decision == "promoted"` → train final
  artifact on all rows, `db.flush()` between deactivating the prior active row and
  INSERT (partial unique index), single `db.commit()` covering swap + eval run.
- Dataset/incumbent builders: labels from `CustomerChurnEvent` (`source != 'auto_suggested'`,
  matching the calibrator's filter at the four documented sites), window/label semantics
  from `calibration_refit.py` (`_LABEL_WINDOW_DAYS=180`, active-window customers);
  incumbent predictor = calibrated heuristic (post-fix aspect 1) over the same features,
  identity below `MIN_LABELS`. Lazy imports of the analysis-engine core.
- Autopromote-hold: re-read `churn_autopromote_hold` row-locked in the same transaction
  (`_autopromote_held` pattern); held → real `decision='held'` eval run with true
  delta/n.
- Beat: register a weekly slot **06:00 UTC Mondays** in `celery_app.py` — before the
  06:30 classifier slot and after the 03:00 global / 07:45 per-org calibration refits
  (the challenger evaluates the *post-refit* incumbent). Fold in purge (inactive > 90d).
- Model columns parity: `OrgClassifierModel`/`OrgClassifierEvalRun` are already generic;
  add nothing beyond the OrgAIConfig columns (aspect 5's migration).

## Out of scope

- Resolver/predict seam, OrgAIConfig columns (aspect 5).
- Any change to `classifier_training.py` itself or the existing three classifier types.
- The probability write path.

## Acceptance criteria

1. `retrain_all_orgs` covers all orgs with labels, per-org failure isolation, tallies
   `{trained, promoted, skipped, held}`.
2. Promote path: deactivation flush → INSERT → commit; active-invariant across repeated
   refits (mirror `test_classifier_training_tasks.py` scaffolds, incl.
   `test_promote_flushes_deactivation_before_inserting_new_active_row`).
3. Hold guard: held run writes `decision='held'` with the real delta and never promotes.
4. Beat entry registered and ordered before the 06:30 classifier slot; purge folds in.
5. Worker suite green; `test_model_parity_classifier.py` extended (if the core adds any
   field, it is mirrored); no module-level sklearn import
   (`test_no_module_level_sklearn_import` equivalent).

## Dependencies / sequencing

- After aspect 3 (imports the core). Before/with aspect 5 (columns must exist before the
  task reads them — getattr-defensive either way).

## Open questions / risks

- R4 (PRD): first real runs of the incumbent may surface latent bugs — the task must
  fail loudly per-org, never silently.
- Promotion cadence: match M5.2 (single-run +0.02) unless the gate study says otherwise.
