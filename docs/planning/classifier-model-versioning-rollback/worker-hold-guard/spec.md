# Aspect spec — worker-hold-guard

**Parent PRD:** `../prd.md` (M2, M3a, G1, G5) · **Depends on:** `data-model-and-migration`.

## Problem slice
Make the weekly auto-promotion honor the hold, race-safely, without freezing the
A/B signal. This is the durability crux.

## In scope
- In `services/worker-service/src/tasks/classifier_training.py::retrain_org`:
  after acquiring the per-(type,org) Redis refit lock and after `evaluate()`, and
  **immediately before** `_promote`, re-read the org's `OrgAIConfig` hold flag for
  this `classifier_type` (row-locked: `.with_for_update()` on Postgres; the SQLite
  test path degrades to a plain read).
- If held: do **not** call `_promote`; instead `_insert_eval_run(decision="held", …)`
  with the computed `macro_f1_delta`/`n` (still commit the eval run). `is_active`
  unchanged.
- If not held: unchanged path (promote iff `decision=="promoted"`).
- The hold re-read + (`held` eval insert | promote) execute in one worker
  transaction so a concurrently-committed rollback is observed.
- Map `classifier_type` → the correct hold column (`sentiment`→
  `sentiment_autopromote_hold`, `category`→`category_autopromote_hold`,
  `urgency`→`urgency_autopromote_hold`).

## Out of scope
- Promotion algorithm, margin (0.02), `MIN_LABELS`, incumbent-heuristic choice.
- `retrain_all_orgs` iteration (still visits every org; only the promote step gates).
- Purge logic (unchanged; active/held version stays `is_active=True` → purge-safe).

## Acceptance criteria (testable)
- **G1:** with the hold set for (org, sentiment) and a challenger that WOULD promote
  (`delta >= 0.02`), running `retrain_org` leaves the active model id unchanged and
  writes an `OrgClassifierEvalRun(decision="held")`.
- **G5 (no regression):** with the hold unset, the same challenger promotes exactly
  as today (new active row, `decision="promoted"`) — existing promotion tests pass
  unchanged.
- Held path still writes a `held` eval run even when `delta >= 0.02` (nudge data).
- Each of the three classifier_types maps to its own hold column (parametrized test).

## Dependencies / notes
- Requires the three hold columns in the worker `OrgAIConfig` mirror (aspect 1).
- Reuse existing test scaffolding in `worker-service/tests/` for classifier training
  (the promotion tests already seed orgs + models + configs).
- `with_for_update()` is a no-op-safe on SQLite (ignored) — tests still exercise the
  branch logic; the row-lock only matters on Postgres.

## Open questions / risks
- Confirm `retrain_org` currently reads `OrgAIConfig` at all; if not, add the read
  (it must not import backend — use the worker mirror). Trace `_promote` call site
  (`classifier_training.py:362-363`) for the exact insertion point.
