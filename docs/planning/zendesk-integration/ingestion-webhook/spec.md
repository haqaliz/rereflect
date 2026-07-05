# Aspect: ingestion-webhook  (optional real-time entry point)

**Slice:** An HMAC-verified inbound webhook so a Zendesk trigger can push new tickets to Rereflect
in real time, reusing the ingestion core. Optional accelerator on top of pull.

## In scope
- `POST /api/v1/webhooks/zendesk/events` in `src/api/routes/source_webhooks.py` (mirror
  `handle_intercom_webhook`):
  - Verify signature: `X-Zendesk-Webhook-Signature` = base64(HMAC-SHA256(`webhook_secret`,
    `X-Zendesk-Webhook-Signature-Timestamp` + **raw body**)); compare against the integration's
    stored `webhook_secret`. Verify over the raw (unparsed) request body.
  - Resolve org via `subdomain` in the payload/headers.
  - Build `provider_context={"subdomain": ...}` and `queue_source_event(source_type="zendesk", ...)`
    → `src.tasks.source_events.process_source_event` (the shared ingestion core).
  - Return 200 fast; dedup handled downstream by `FeedbackSourceEvent` (ticket id).
- Operator setup: the connect flow surfaces the webhook URL + secret to paste into a Zendesk
  trigger/webhook (documented in landing-docs aspect).

## Out of scope
- Pull task; per-comment; filters; signature schemes beyond Zendesk's documented HMAC.

## Acceptance criteria (mirror Intercom webhook tests)
- Valid signature + new-ticket payload → 200 and a queued `process_source_event` with
  `source_type="zendesk"` and the correct subdomain context.
- Invalid/missing signature → 401/403, nothing queued.
- Unknown subdomain / no active `zendesk` source → 200 logged no-op (no leak), nothing created.
- A ticket already ingested via pull is deduped (same `FeedbackSourceEvent` key) — no duplicate.

## Dependencies / sequencing
- Depends on **backend-connection** (webhook_secret) + **ingestion-core**.
- Parallel with **ingestion-pull**.
