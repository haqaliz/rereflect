# Aspect Spec — ingestion-receiver

Parent PRD: `../prd.md`

## Problem slice & outcome

A self-hosted operator can POST product-usage events to Rereflect with an existing ingest-scoped API key. The endpoint validates, dedups, and hands events to the worker — returning accurate accepted/skipped counts. No vendor OAuth.

## In scope

- `POST /api/v1/webhooks/usage` router (`services/backend-api/src/api/routes/usage_webhooks.py`), registered in `api/main.py`.
- Auth: `Depends(verify_api_key)` + `require_scope("ingest")` (`api/public/auth.py:74-129`); org = `auth.organization_id`.
- Pydantic request models for the **normalized, batchable** body (see PRD API Contract): `type ∈ {identify, track}`, `email`/`userId`, `event`, `name`, `timestamp`, `messageId`, `properties`/`traits`.
- Validation + bounds: ≤1000 events/request (else `413`); per-event `properties` ≤16 KB (truncate+count); reject unknown `type`.
- Email resolution: `email` or `traits.email`. Unresolvable → skipped, counted by reason.
- Dedup: `external_event_id = messageId`; quick DB existence check + unique constraint (full dedup in worker).
- Raw `usage_event` model + Alembic migration (`down_revision = y4z5a6b7c8d9`).
- Enqueue accepted events to Celery `process_usage_event` by name via `get_celery_app().send_task(...)`.
- Response `202` → `{accepted, skipped, skipped_reasons}`.

## Out of scope

- The rollup, score, and health wiring (aspect `usage-rollup-and-score`, `health-component`).
- Anonymous/userId-only storage and identity stitching.
- Any frontend.

## Acceptance criteria (testable)

1. POST with a valid ingest key + 2 events (1 with email, 1 without) → `202`, `{accepted:1, skipped:1, skipped_reasons:{no_email:1}}`, and 1 `usage_event` row written for the org.
2. POST without ingest scope → `403`; with no/invalid key → `401`.
3. POST with >1000 events → `413`, nothing written.
4. Duplicate `messageId` (same org) → not double-written; counted as duplicate, still `202`.
5. Event for org A cannot create rows under org B (tenancy: rows carry `auth.organization_id`).
6. A `properties` blob >16 KB is truncated/dropped and the event still ingests (counted).
7. Accepted events are enqueued to `src.tasks.usage_metrics.process_usage_event` (assert `send_task` called with expected args; mock broker).

## Dependencies & sequencing

- Independent of the rollup task at the API layer (enqueues by name — the task can land in parallel). The migration here creates `usage_event`; the rollup aspect adds `customer_usage`. Keep them as **separate migrations** to avoid coupling.
- Must merge before end-to-end manual verification.

## Open questions / risks

- Dedup when `messageId` absent: fall back to a hash of `(email,event,name,timestamp)`? Decide here; default = require `messageId`, else count as `skipped_reasons.no_message_id`.
- Timestamp parsing: accept ISO-8601; missing → server `received_at`.
