# Aspect Spec — worker-trainer-and-schedule

**Parent PRD:** `../prd.md` (M5.2 per-org-corrections-classifier)
**Sequence:** after `data-layer` + `training-and-eval-core`.

## Problem slice / outcome

The Celery driver that runs the core across all orgs on a schedule, persists versioned artifacts with
an **atomic** active-model swap, records an eval-run row every time, and purges old versions — mirroring
`tasks/churn_calibration.py` + `services/calibration_refit.py`.

## In-scope

1. **`tasks/classifier_training.py::retrain_all_orgs()`** (worker): iterate orgs via the existing
   all-orgs helper; per-org `try/except` so one failure never aborts the batch; return
   `{"trained": n, "promoted": m, "skipped": k}`.
2. **Per-org driver** `retrain_org(org_id, db)`:
   - Build dataset (aspect B) → gate on per-type `MIN_LABELS` → below gate: write a `skipped` eval-run,
     return (no model row).
   - Train challenger (aspect B) → evaluate vs incumbent (inject a live `SentimentAnalyzer`-based
     incumbent predictor).
   - **Atomic promotion transaction** when `decision='promoted'`: in one transaction — deactivate the
     current active `(org, 'sentiment')` row, insert the new `is_active=True` row (with denormalized
     macro_f1/precision/recall/accuracy + label_count + fit_at), commit. Never a window with 0/2 active
     (partial-unique enforces ≤1).
   - Always insert an `org_classifier_eval_runs` row (promoted/retained/skipped) with delta + n +
     duration_ms + notes.
   - Per-org advisory guard to prevent overlapping refits of the same org.
3. **Purge** `purge_old_classifier_models()` — delete inactive rows older than 90 days (mirror churn
   purge), or fold into the weekly task.
4. **Schedule:** register the task module in `celery_app.py` `include=[...]`; add a `beat_schedule`
   entry `crontab(day_of_week=1, hour=6, minute=30)` (uncrowded Monday 06:30 UTC — verify slot is free).

## Out-of-scope

- The pure train/eval math (aspect B). Predict-at-ingest / mode injection (aspect D). API/UI (aspect E).

## Acceptance criteria (testable)

- `retrain_org` on synthetic corrections: below-gate → one `skipped` eval-run, zero model rows;
  better-challenger → exactly one new active row, prior active flipped inactive, one `promoted` eval-run;
  worse-challenger → no new active row, one `retained` eval-run.
- After a promotion, `SELECT count(*) WHERE is_active AND org AND type='sentiment'` == 1 (invariant holds
  across repeated refits).
- A raised exception inside one org's `retrain_org` does not abort `retrain_all_orgs` for other orgs
  (per-org isolation test).
- Purge removes only inactive rows older than 90 days; active + recent rows retained.
- Beat entry present with the correct crontab; task importable; no module-level sklearn import.

## Dependencies & sequencing

- **Blocked by:** data-layer, training-and-eval-core. **Blocks:** none (E reads what this writes).
- Reuse `get_db_session()` context manager; lazy heavy imports; CPU-only.

## Open questions / risks

- Confirm the all-orgs iteration helper name used by `refit_all_orgs`. Confirm 06:30 UTC Monday is
  unused in the current `beat_schedule`. Advisory-lock mechanism (Redis vs DB) — match existing churn
  approach if any, else a simple Redis key.
