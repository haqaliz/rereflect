# Aspect: ingestion-pull  (default entry point)

**Slice:** A Celery beat task periodically polls Zendesk with the stored token and routes **new**
tickets through the ingestion core. Works with no public ingress — the default for self-host.

## In scope
- New Celery task `src/tasks/zendesk_sync.py` (do NOT extend the legacy `ZendeskConnector` in
  `tasks/integrations.py`; retire/leave-unwired that stub):
  - For each active `zendesk_integrations` row: decrypt token, poll
    `GET /api/v2/incremental/tickets?start_time={cursor}` (unix seconds), page until caught up.
  - Cursor = `last_synced_at` (init to connection time on first run — **new tickets only**, no
    historical backfill).
  - For each ticket, synthesize a source event and call the ingestion-core / `process_source_event`
    creation path (reusing `FeedbackSourceEvent` dedup) — **not** ad-hoc `FeedbackItem` creation.
  - Update `last_synced_at`, `last_sync_status`, `last_error`; **honor `429 Retry-After`** and
    throttle **per integration** (account-wide Zendesk rate limits), plus 5xx backoff.
  - Unmatched subdomain / no active `zendesk` source → logged no-op recorded in
    `last_sync_status`/`last_error` (not a crash, not a silent success).
- Register in `celery_app.py` beat schedule (e.g. every 15 min) + include list.
- Manual "Sync now" support (should-have): callable on demand from the connect route.

## Out of scope
- Webhook path; per-comment; filters; backfill.

## Acceptance criteria
- Given a fake Zendesk incremental response (patched client), the task creates one `FeedbackItem`
  per new ticket via the shared core, with correct `source`/`external_id`/`customer_email`.
- Re-running with the same cursor/tickets creates **no duplicates** (FeedbackSourceEvent dedup).
- Cursor advances to the newest ticket's `updated_at`/`end_time`; persisted on the integration.
- Auth failure marks `last_sync_status`/`last_error` without raising; transient errors retried/backed off.
- First run ingests only tickets at/after connection time (no history flood).

## Dependencies / sequencing
- Depends on **backend-connection** (token, cursor fields) + **ingestion-core** (creation path, source matching).
- Parallel with **ingestion-webhook** (both consume the core).
