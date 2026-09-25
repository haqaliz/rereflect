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

## Scope change during build (2026-09-25)
`_process_event_for_source` is also called by the Zendesk and Intercom **pull** syncs, which had
the same flush → publish → commit order. Rather than leave a flag whose default kept the bug,
the helper no longer publishes at all: `process_source_event`, `zendesk_sync` (flush → explicit
commit, then `_dispatch_analysis`) and `intercom_sync` (next to its existing post-commit
re-analysis block) each publish `created_feedback_ids` after their own commit. Ordering tests were
RED first for all three. `test_zendesk_sync.py::test_analysis_queued_for_each_created_item` now
pins "the helper returns ids and does not publish" instead of the old inline publish.
