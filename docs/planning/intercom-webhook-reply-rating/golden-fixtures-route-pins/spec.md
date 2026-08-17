# Aspect spec — Golden fixtures + route kwargs pins

**Feature:** `intercom-webhook-reply-rating` (prd.md R5) · **Aspect:** `golden-fixtures-route-pins`

## Problem slice

The real Intercom replied/rating webhook payloads are conversation-wrapped (item.id =
conversation id; parts at conversation_parts.conversation_parts[]; rating at
conversation_rating). Nothing pins that shape today (only `created` has a golden
fixture), and the backend replied/rating route tests assert only `event_type` — not
external_event_id/event_data/provider_context. This aspect pins the contract FIRST so
the enrichment module (next aspect) is built against a verified shape.

## In-scope

- Two new cross-service fixtures in `services/worker-service/tests/fixtures/`:
  `intercom_webhook_reply_envelope.json` + `intercom_webhook_rating_envelope.json`,
  conversation-wrapped per the real API shape:
  - Reply: `data.item.type="conversation"`, `id` = conversation id,
    `conversation_parts.conversation_parts[]` with a `part_type:"comment"` part
    (id, body with HTML, author user with email, created_at).
  - Rating: `data.item.type="conversation"`, `id` = conversation id,
    `conversation_rating` = {rating, remark, created_at}.
- Loader pairs with the existing raise-if-missing contract (worker
  `test_intercom_envelope_seam.py:52-69`, backend `test_intercom.py:591-615`) — the
  worker seam test + backend contract test each read BOTH new fixtures.
- Backend route test pins: `test_intercom.py` replied/rating tests gain assertions on
  `external_event_id` (== item.id == conversation id), `event_data` (full envelope),
  `provider_context` (conversation_id + workspace_id) — mirroring the created test's
  full-kwargs pin (:454-502).
- One worker seam test: "given the reply envelope, the adapter identifies the
  conversation id + a reply part" (drives the new module's inputs).

## Out of scope

- The enrichment module itself (webhook-enrich-module aspect); the core branch
  (core-branch-dispatch); anything else.

## Acceptance criteria (testable)

1. Both fixtures exist in `worker-service/tests/fixtures/`; both suites read them
   (worker + backend), with raise-if-missing (never skip).
2. Backend replied/rating route tests assert the full kwargs (external_event_id,
   event_data, provider_context), matching the real conversation-wrapped shape.
3. Worker seam test extracts conversation id + reply part from the reply fixture.
4. Backend + worker suites green; existing created-envelope contract unchanged.

## Dependencies & sequencing

- First aspect (pins the shape the module consumes). No dependency on others.

## Open questions / risks

- Fixture field names must match what the adapter/pull path already parses
  (`intercom_parts.py` filters `part_type == "comment"`, `type == "conversation_part"`)
  — reuse those exact key names so the enrichment module can reuse the seams
  unchanged.
