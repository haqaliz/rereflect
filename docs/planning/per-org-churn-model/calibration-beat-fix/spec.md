# Spec — calibration-beat-fix (prerequisite)

## Problem slice

The calibrated-heuristic incumbent has never run: `tasks/churn_calibration.py` defines
`refit_all_orgs`, `refit_global_calibration`, `purge_old_calibration_models` as plain
functions with no Celery decorator, while `celery_app.py` registers them in
`beat_schedule` (lines 211-232) → `NotRegistered` on dispatch. Every M5.3 A/B against "the
calibrated heuristic" is meaningless until this is fixed. (In-repo corroboration:
`tasks/usage_metrics.py:482-485`.)

## In scope

- Decorate the three functions with `@shared_task` (matching the `tasks/` convention;
  check how sibling tasks, e.g. `classifier_training.py`, declare theirs).
- Keep the existing `celery_app.py` beat entries unchanged (they already reference
  `src.tasks.churn_calibration.<name>`; verified registered after the fix).
- Pin registration with a worker-suite test: assert the three task names are registered
  on the app (or assert the functions carry `@shared_task` and are in the beat schedule),
  without invoking Celery.
- Existing direct-call tests (`test_churn_calibration_tasks.py`) stay green and
  unmodified except where the registration assertion lives.

## Out of scope

- Any behavior change to the refit/global/purge logic itself.
- The F1-drop guard, window tuning, `MIN_LABELS` parity, or other calibrator debt.
- The `NotRegistered`-style sweep of other task files (that is a separate pass).

## Acceptance criteria

1. `refit_all_orgs`, `refit_global_calibration`, `purge_old_calibration_models` are
   `@shared_task`-decorated and appear in `app.tasks` registration.
2. Beat schedule entries for the three task names resolve to registered tasks (a test
   asserts registration — no `NotRegistered` at dispatch time).
3. `pytest tests/ -q` in `services/worker-service` is green, including the pre-existing
   direct-call tests, with no edits to production logic beyond the decorators.
4. No new columns, no migration, no frontend change.

## Dependencies / sequencing

- First aspect in the card. The gate study (aspect 2) and the ML head's incumbent
  (aspects 3-5) both depend on the incumbent being real — but the study can start in
  parallel since it models the heuristic directly.

## Open questions / risks

- Whether `@shared_task` vs the codebase's local `celery_app` task pattern differs for
  this file — read `classifier_training.py` and `usage_metrics.py` first and mirror
  their declaration style.
- Risk R4 (PRD): waking a never-run path may surface latent bugs on first real run —
  out of scope here; tests pin behavior as it exists.
