# Aspect: webhook-realtime

**Slug:** `zendesk-status-sync` · **Aspect dir:** `webhook-realtime`
**Sequencing:** after reconcile-core-and-model (needs module + sidecar model). Independent of poll-task, but should reuse a shared reconcile/apply helper.

## Problem slice & outcome

Near-real-time status-sync: when Zendesk sends a ticket-update webhook, reconcile that single ticket's
status immediately (subject to the same opt-in + change-gate), instead of waiting for the 15-min poll.
The poll remains the catch-up/NAT fallback.

## In scope
1. **Extend the existing receiver** `POST /api/v1/webhooks/zendesk/events` (`services/backend-api/src/api/routes/…webhooks`):
   - Keep current HMAC-SHA256 verification (fail-closed on missing secret) and the ingestion `ticket.created` path untouched.
   - Add a branch for ticket status-change events (confirm exact event type/payload during dig — likely `ticket.status_changed` / a `ticket` update carrying `status` + `id`).
   - Resolve org via the `ZendeskIntegration` matching the webhook (subdomain/secret). Gate on `is_active AND status_sync_enabled` — if off, ACK 200 and ignore (no error).
   - Look up the linked feedback: `feedback WHERE source='zendesk' AND source_external_id = ticket_id AND organization_id=:org`. If none, ACK 200 ignore.
   - Reconcile via the SHARED path used by the poll: `decide_update` against the `FeedbackZendeskSync` row + `resolve_target_status(status, integ.status_mapping)`; apply through the same source-tagged writer (backend-side `apply_status_change` or the shared writer) and upsert the sidecar. Seed (first observation) → record only, no apply.
   - Idempotent with the poll: whichever sees the change first applies + updates the sidecar; the other → noop. ACK 200 always on a well-formed, verified event.
2. Backend-side apply writer: reuse `workflow_service.apply_status_change` (already emits `status_changed` event) — pass `actor_label` + `source=zendesk` metadata; **do NOT** call `dispatch_status_webhooks` (outbound webhook deferred, Jira parity).

## Out of scope
- Poll task, client, routes toggle, frontend.
- Any new webhook registration/config UI (operators already set the webhook up for ingestion).

## Acceptance criteria (testable)
- Verified `ticket.updated` with `status=solved` for a linked ticket, org has sync ON, sidecar shows prior `open` → feedback → `resolved`, one `status_changed` event (`source=zendesk`), sidecar updated, HTTP 200.
- Same event when `status_sync_enabled=false` → HTTP 200, no change, no event.
- First-ever observation via webhook (no sidecar row) → seed: sidecar written, no apply, 200.
- Event for a ticket with no linked feedback → 200, no-op.
- Bad/missing HMAC → rejected exactly as today (unchanged), fail-closed on missing secret.
- Webhook then poll (or poll then webhook) on the same change → single apply total (change-gate), no duplicate event.
- Ingestion `ticket.created` path behavior unchanged (characterization).

## Dependencies & sequencing
- Needs: reconcile-core-and-model. Should land after or alongside poll-task so the shared reconcile/apply helper exists (avoid duplicating the change-gate).
- Cross-service note: the receiver runs in backend-api; the poll writer lives in worker-service. Put the pure reconcile in the backend mirror of `zendesk_status_core.py`; use backend `workflow_service.apply_status_change` for the apply so no worker import is needed.

## Open questions / risks
- **R5:** confirm the exact Zendesk webhook event type + payload for status changes vs the existing `ticket.created` ingestion trigger. The receiver may currently assume creation events only — the dig must map its current parsing before adding the branch.
- Ensure the status branch cannot be spoofed to ingest (keep ingestion vs status branches distinct by event type).
