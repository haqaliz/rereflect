# Spec — source-events-dispatch

**Outcome:** webhook-ingested `FeedbackItem`s are committed before `analyze_single_feedback` is
published, so analysis never returns `not_found` for a fresh item (PRD S1).

## In scope
`services/worker-service/src/tasks/source_events.py`: `_process_event_for_source` stops calling
`.delay` inline; `process_source_event` publishes the created feedback ids **after** its existing
`db.commit()` (`:127`). Ordering test RED first.

## Out of scope
Pending-feedback path (no analysis dispatch); the text-changed re-analysis path (already post-commit).

## Acceptance criteria
1. Test: an `auto_import` event → `calls.index("commit") < calls.index("delay")`, and `delay`
   called with the new feedback id. RED on master, GREEN after.
2. Existing `test_source_events*.py` / webhook tests pass (result dicts unchanged, incl. `feedback_id`).
3. A `.delay` failure after commit is logged, not raised (sweeper recovers the item).
