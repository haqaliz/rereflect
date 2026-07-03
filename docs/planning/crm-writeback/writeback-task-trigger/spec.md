# Aspect: writeback-task-trigger (worker task + backend health hook)

**Slice of:** crm-writeback PRD · **Services:** `services/worker-service` (task) + `services/backend-api` (enqueue hook)
**Depends on:** hubspot-write-client (PATCH surface), writeback-config-api (columns/flag).
**Blocks:** nothing (final backend/worker piece).

## Problem slice / outcome

When a customer's health score changes, push it to HubSpot — idempotently, gated to opted-in
orgs, and soft-pausing (never breaking read-sync) on permanent failures.

## In scope

- **Celery task** `push_health_to_hubspot(org_id, customer_email)` (new module `src/tasks/hubspot_writeback.py`, registered in `celery_app.include` + a name Celery can address):
  1. Load the org's `HubSpotIntegration`; no-op unless `is_active` **and** `writeback_enabled` **and** `writeback_field_name` set.
  2. Load the `crm_enrichment` row for `(org, email)`; no-op if absent or no `hubspot_contact_id` (customer not matched).
  3. Load current `CustomerHealth.health_score`; **skip if** it equals `last_written_health_score` (idempotency) or the change is < 2 points from last-written.
  4. `update_contact_property(contact_id, writeback_field_name, score)`. On success: set `last_written_health_score`, `last_health_written_at`, bump `contacts_written`, set `last_writeback_status="ok"`, `last_writeback_at=now`.
  5. **Soft-pause** on permanent failure: `403` scope → `last_writeback_status="error: missing_write_scope"`; property/contact `404` → `field_not_found` / `contact_not_found` (per-customer skip for contact-404). Never set `is_active=False`. Transient (429/5xx) → retry with backoff (mirror `sync_hubspot_org` decorator).
- **Enqueue hook** in `health_score_service.update_customer_health()` right after the health-drop-alert call (`:335`), existing-customer branch, where `old_score`/`new_score` are in scope: if `abs(new-old) >= 2`, `celery_app.send_task("src.tasks.hubspot_writeback.push_health_to_hubspot", args=[org_id, email])`. Enqueue **by name** (no worker import from backend); wrap in try/except so an enqueue failure never breaks recompute. Cheap pre-check (skip enqueue if the org has no active+enabled HubSpot integration) to avoid queue spam.
- (should-have S2) **Backfill on enable:** `writeback-config-api`'s `PATCH /writeback {enabled:true}` enqueues a bounded fan-out `push_health_to_hubspot` for all matched customers of the org.

## Out of scope

- Multi-field push; Salesforce; company properties; changing the score math or the ≥2-pt threshold.

## Acceptance criteria (testable)

- Task no-ops (no PATCH) when: integration inactive, writeback disabled, no field name, no enrichment row, no contact id, or score unchanged vs `last_written_health_score`.
- Happy path: PATCH called once; `last_written_health_score`/status/counters updated.
- 403 → status `error: missing_write_scope`, `is_active` unchanged, **read-sync untouched** (assert an inbound sync still succeeds after).
- Contact 404 → that customer skipped, status noted, other customers unaffected.
- 429 → retried (assert `retry` invoked), status `retrying`.
- Enqueue hook: a ≥2-pt change with an active+enabled integration calls `send_task` once with the right name/args; a disabled/absent integration does **not**; an enqueue exception does not raise out of `update_customer_health`.
- Health-score characterization tests remain byte-identical (no math touched).

## Notes / risks

- **Verify backend can `send_task`** to the broker (Celery app importable in backend). If not, fall back to a daily batch beat scanning `CustomerHealth` — same task body, different trigger. Resolve in tech-plan before coding the hook.
- Rapid successive changes may enqueue overlapping pushes; last-writer-wins + the idempotent skip make this safe though unordered (acceptable for slice 1).
