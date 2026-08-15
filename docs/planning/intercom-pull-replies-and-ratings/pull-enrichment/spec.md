# Aspect spec — Pull enrichment integration

**Feature:** `intercom-pull-replies-and-ratings` (prd.md R3 + R5) · **Aspect:** `pull-enrichment`

## Problem slice

The `_sync_org` pull loop (`services/worker-service/src/tasks/intercom_sync.py:111-214`)
must fetch parts for the conversations it sees, merge new reply content into the
existing per-conversation FeedbackItem, record the rating, and dispatch re-analysis for
changed items — idempotently, within the run's bounds.

## In-scope

- In `_sync_org`, after the existing event loop (which creates/refreshes the item via
  the shared core), an enrichment pass per seen conversation:
  1. Fetch parts via the client (R1a search param or R1b detail method — whichever the
     client aspect landed).
  2. Load the conversation's FeedbackItem (via `source == "intercom"` +
     `source_external_id == conversation_id` + the source's org — the existing lookup
     shape).
  3. Diff parts against `source_metadata["replies"]` part_ids; append ONLY new replies
     using the merge format (adapter aspect), record the full reply list + rating in
     `source_metadata`.
  4. If content changed → collect the item id for the re-analysis dispatch (reanalysis
     seam); unchanged → nothing.
- **Idempotency:** same conversation seen again (boundary re-fetch, redelivery, or a
  new run) → no duplicate text, no re-analysis (part_id membership).
- **Bounded (R5):** the search window + 20-page cap bound conversations; the R1b
  detail-fetch path (if used) enforces a per-run cap with a logged, non-silent drop
  count (usage-decline per-run cap precedent); 429/5xx flow through the client's
  IntercomTransientError → task retry.
- **Admin/bot replies:** merged as content, never attributed (adapter rule — the
  enrichment must not pass author emails to `customer_email`).
- **Rating:** metadata-only (never in text).
- Tests: enrichment happy path (one item, text includes replies, metadata has replies +
  rating); redelivery idempotency; no-change → no dispatch; admin-author content;
  per-run cap with logged drop; the `conversations_ingested` counter semantics
  unchanged; all six existing one-item characterization tests pass unchanged.

## Out of scope

- Client/API (client aspect); extraction/merge format (adapter aspect); the re-analysis
  call itself (reanalysis-seam aspect — this aspect only dispatches through it);
  backfill of older conversations (prd.md honest limit); UI.

## Acceptance criteria (testable)

1. One conversation with parts → exactly ONE FeedbackItem whose text contains the new
   replies (merge format) and whose metadata contains replies + rating.
2. Second run / redelivery → no text change, no re-analysis dispatch (asserted).
3. Only items with new content dispatch re-analysis (seam test).
4. R1b path (if used): per-run cap respected, dropped count logged, task retries on
   transient errors.
5. All six existing one-item characterization tests pass unchanged; worker suite green.

## Dependencies & sequencing

- After `client-conversation-parts`, `adapter-reply-rating-extraction`, and
  `reanalysis-seam` (consumes all three).

## Open questions / risks

- Where the enrichment pass lives in `_sync_org` vs a helper function — decide in plan
  (helper keeps `_sync_org` readable; the seam test targets the helper).
- `conversations_ingested` semantics: enrichment should not inflate it (it counts
  created items today) — the plan pins the counter behavior.
