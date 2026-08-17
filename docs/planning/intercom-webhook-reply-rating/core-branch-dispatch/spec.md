# Aspect spec — Core branch + enriched status + post-commit dispatch

**Feature:** `intercom-webhook-reply-rating` (prd.md R1 + R3 + R4) · **Aspect:** `core-branch-dispatch`

## Problem slice

The shared core (`source_events.py`) must route intercom replied/rating events into the
enrichment module instead of the trigger/dedup/create path, log them with a dedup-safe
status, and dispatch bounded re-analysis strictly after the end-commit.

## In-scope

- `_process_event_for_source` (`source_events.py:275-428`): at the top, an
  intercom-specific guard — when `source.source_type == "intercom"` and `event_type in
  ("conversation.user.replied", "conversation.rating.added")`:
  1. Lazy-import + call `intercom_webhook_enrich.enrich_webhook_item(db, source,
     event_type, event_data)`.
  2. Log a `FeedbackSourceEvent`:
     - `status="enriched"`, `external_message_id = conversation id`,
       `feedback_id` set, `event_type` set — when enriched.
     - `status="ignored"`, message_id = conversation id — for `noop/*` outcomes.
     - `error/auth_error` → log `status="failed"`? Decide in plan (a failed delivery
       should be visible; `ignored` vs `failed` semantics — the model's comment lists
       `pending, processed, ignored, failed`).
  3. Return `{"source_id": source_id, "status": <outcome>, "changed": bool,
     "feedback_id": int|None}`; on `IntercomTransientError` re-raise (task retry
     path); on unexpected error, follow the existing rollback+retry contract.
- `process_source_event` (`:36-119`): collect `changed_feedback_ids` from per-source
  results; **after** the end-commit (`:105`) + cache invalidation, dispatch
  `reanalyze_feedback(db, feedback_id)` for each changed id (try/except per item —
  the pull's guarded post-commit dispatch pattern, intercom_sync.py:397-406).
- The `enriched` status is NEW vocabulary — a comment on the model's status column
  (models/__init__.py:281) and a docstring in the core noting it is never dedup-relevant
  (the dedup filter matches only processed/pending, source_events.py:315) and never
  blocks a later `created` delivery (out-of-order safety).
- Tests (the seam-test harness — `_patch_db_session` + `_no_op_side_effects` + direct
  `process_source_event`):
  - created→replied→rating sequence → exactly 1 item, enriched text + rating metadata.
  - reply before created (out-of-order) → noop/ignored; then created → item created
    (the `enriched`-status dedup-safety test).
  - redelivery of the same reply → no text change, exactly one re-analysis dispatch.
  - rating-only → metadata updated, NO re-analysis dispatch.
  - re-analysis dispatched after commit (ordering test mirroring
    test_intercom_enrichment.py::test_dispatch_happens_after_commit).
  - transient (429) → task retry (re-raise), no partial commit.
  - the created path + all six one-item characterization tests unchanged.

## Out of scope

- The enrichment module body (webhook-enrich-module aspect — consumed here);
  fixtures; docs.

## Acceptance criteria (testable)

1. Intercom replied/rating events bypass trigger + dedup and reach the enrichment
   module (asserted via status + effects).
2. Event log rows: `enriched` status with feedback_id; `ignored` for noops; the
   `enriched` status never blocks a later created delivery (pinned).
3. Re-analysis dispatched exactly once per text-changed item, after commit; none for
   rating-only.
4. All six one-item characterization tests + the created-path tests unchanged; worker
   suite green.

## Dependencies & sequencing

- After `webhook-enrich-module`. Before `docs-tracking-changelog`.

## Open questions / risks

- `error/auth_error` log status: `failed` (model-comment vocabulary) vs `ignored`
  with a reason — decide in plan; the settings page's webhook card doesn't surface
  event-log status today, so this is audit-only either way.
