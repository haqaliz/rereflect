# Aspect spec — Webhook enrichment module

**Feature:** `intercom-webhook-reply-rating` (prd.md R2) · **Aspect:** `webhook-enrich-module`

## Problem slice

A seam-tested module that turns a replied/rating webhook event into a merge into the
existing per-conversation FeedbackItem — conversation id extraction, item lookup,
payload-first parts/rating extraction with a `get_conversation` fallback, and merge via
the #16 seams — returning a status dict the core branch (next aspect) dispatches on.

## In-scope

- New `services/worker-service/src/services/intercom_webhook_enrich.py` with one
  function:
  `enrich_webhook_item(db, source, event_type, event_data) -> dict` returning
  `{"status": "enriched"|"noop/no_item"|"noop/not_found"|"error/auth_error"|..., "changed": bool, "feedback_id": int|None}`.
- Steps (pinned by tests):
  1. Conversation id: `event_data["data"]["item"]["id"]` (conversation-wrapped shape).
  2. Item lookup (index-backed, org-scoped): `FeedbackItem(organization_id=
     source.organization_id, source="intercom", source_external_id=conversation_id)`;
     none → `noop/no_item`.
  3. Parts + rating: payload-first from `item.conversation_parts.conversation_parts[]`
     / `item.conversation_rating`; if absent → `IntercomClient.get_conversation(
     conversation_id)` fallback (single fetch; 404 → `noop/not_found`, 401/403 →
     `error/auth_error`, 429/5xx → raise `IntercomTransientError` so the task retries).
  4. Merge: `extract_reply_parts` + `extract_rating` (intercom_parts.py) →
     `_enrich_conversation_replies(db, item, parts, rating)` (intercom_sync.py —
     lazy import; idempotent by part_id; rating metadata-only).
  5. `changed` True only when text changed; `feedback_id` set on success.
- Never creates items; never touches `customer_email`.
- Module imports `intercom_parts.py` (pure) directly; lazy-imports
  `intercom_sync._enrich_conversation_replies` + `clients.intercom.IntercomClient`
  (house lazy-import convention; never a swallowed-`except` import).
- Tests (self-contained SQLite + injectable client per the writeback/enrichment test
  patterns): conversation id extraction, item lookup (found/not-found),
  payload-first extraction, fallback fetch (parts absent / 404 / 401 / 429-raise),
  merge idempotency (re-run no-op), rating metadata-only, changed-flag semantics,
  never-creates (count stays 1), admin-author never attributed.

## Out of scope

- The core branch + `enriched` event status + post-commit re-analysis dispatch
  (core-branch-dispatch aspect); fixtures (golden-fixtures-route-pins — consumed
  here); docs.

## Acceptance criteria (testable)

1. `enrich_webhook_item` returns the status dict per the contract above for every
   branch (enriched / no_item / not_found / auth_error / transient-raise).
2. Payload-first + fallback paths both merge correctly; idempotent on re-run.
3. `FeedbackItem` count never increases (invariant); `customer_email` never written.
4. Worker suite green; the import-sweep guard passes.

## Dependencies & sequencing

- After `golden-fixtures-route-pins` (consumes the pinned shape).
- Consumed by `core-branch-dispatch`.

## Open questions / risks

- The fallback fetch is per-event (single conversation) — no per-run cap needed, but
  a flood of replies on different conversations each triggers one fetch; acceptable
  (bounded by Intercom's webhook rate and the task's own retry).
