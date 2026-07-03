# PRD — Bidirectional CRM Writeback (HubSpot, slice 1)

**Slug:** `crm-writeback` · **Branch:** `feat/crm-writeback` · **Type:** feat (freeform)
**Status:** Draft — awaiting review-gate approval
**Date:** 2026-07-03
**Source:** `rereflect-next` recommendation. Deferred-v2 slice named at `AI-TRACKING.md:185` (HubSpot) & `:195` (Salesforce).

> Decisions in §Requirements marked **[default]** were taken on best judgment while the PM was
> away during the interview. They are the recommended options and are flagged for confirmation
> at the review gate — none are locked.

## Problem Statement

Rereflect computes a per-customer **health score** (and churn signals), but that intelligence
lives only inside Rereflect. The people who act on it — CSMs, account owners — work in their
**CRM** (HubSpot). Today CRM data flows one way only: HubSpot → Rereflect (the health
`crm_component`). There is no path back, so the health score never reaches the system of
record where renewals, tasks, and workflows are actually run.

**Evidence it's real:** the CRM integrations shipped inbound-only and both explicitly listed
"push health scores back" as deferred v2 (`AI-TRACKING.md:185`, `:195`). The read-side plumbing
(provider-tagged `crm_enrichment`, matched `hubspot_contact_id`, per-org encrypted token) is
already in place — only the outbound half is missing.

## Goals & Success Metrics

- **G1 — Close the loop:** an opted-in org's matched HubSpot contacts carry a live Rereflect
  health-score property. *Metric:* for an org with writeback enabled and the field configured,
  ≥95% of customers that have both a `CustomerHealth` row and a matched `hubspot_contact_id`
  show a non-stale value in HubSpot (pushed within one trigger cycle of their last change).
- **G2 — Zero blast radius on the read side:** enabling/disabling writeback, or a writeback
  failure, never alters inbound enrichment or health scores. *Metric:* the existing CRM
  characterization tests (`test_crm_provider_generalization.py`) stay byte-identical; a forced
  write failure leaves read-sync green.
- **G3 — Safe by default:** writeback is **off** until an operator opts in and names a field;
  pushes are idempotent (no redundant PATCH when the value is unchanged).

## User Personas & Scenarios

- **Self-hosting operator / admin** — connects HubSpot with a private-app token, creates a
  custom contact property, enters its name in Rereflect, flips writeback on. Owns scopes/fields.
- **CSM (indirect)** — sees the Rereflect health score inside HubSpot contact views, list
  filters, and workflows, without opening Rereflect.

## Requirements

### Must-have (slice 1)
- **M1 — One field, one provider:** push `health_score` (integer 0–100) to **HubSpot**, as a
  **contact property** (matches the email-based read side). Salesforce is out of scope.
- **M2 — Opt-in per org, off by default.** `writeback_enabled` defaults `False`; no pushes occur
  until an operator enables it *and* a field name is set. **[default]** config lives on
  `HubSpotIntegration` (mirrors the existing `arr_property_name` precedent).
- **M3 — Detect & validate the operator's field [default].** The operator creates the custom
  property in HubSpot and enters its internal name (default suggestion `rereflect_health_score`).
  Rereflect validates it exists and is writable (`GET /crm/v3/properties/contacts/{name}`); if
  missing/read-only, surface a clear "create field / grant scope" status. **No schema-write
  scope required** — only `crm.objects.contacts.write`.
- **M4 — Trigger on change, near-real-time [default].** When `update_customer_health()` changes
  a customer's score (the existing `old_score`/`new_score` gate, `health_score_service.py:313–335`),
  enqueue a writeback push for that `(org, email)` **iff** the org has an active HubSpot
  integration with `writeback_enabled`. Enqueue by task name (no cross-service import coupling);
  never call HubSpot inline (the function runs pre-commit).
- **M5 — Idempotent:** the push task re-reads the current `health_score` and the last-written
  value; **skip the PATCH when unchanged**. Gate on the same ≥2-point change threshold used for
  history/alerts.
- **M6 — Soft-pause on failure [default].** On `403`/missing-scope or missing/read-only field,
  set a `writeback` status (`error: missing_write_scope` / `field_not_found`) and stop pushing —
  **leave the inbound read-sync fully working.** Transient `429`/`5xx` retry with backoff
  (mirror `HubSpotTransientError`). Do **not** flip `is_active` (that is the read-sync's flag).
- **M7 — Status surfaced:** writeback columns (`last_writeback_at`, `last_writeback_status`,
  `last_writeback_error`, `contacts_written`) exposed on `GET /status` and rendered on the
  HubSpot detail page next to the existing sync-status grid.

### Should-have
- **S1 — Validate/Test button** on the detail page that runs the field-existence check on demand
  (mirrors the existing "Test connection" button).
- **S2 — Backfill on enable:** when writeback is first turned on, enqueue a one-shot push for all
  currently-matched customers (bounded fan-out), so scores don't wait for the next change.

### Nice-to-have (explicitly deferred, see Out of Scope)
- Multi-field push (churn probability, risk level, top drivers); Salesforce writeback; real-time
  (vs. enqueued) push; company-level properties; two-way conflict policy beyond last-writer.

## Technical Considerations

**Services changed:** `backend-api` (model + migration + API + health-service hook),
`worker-service` (write client + push task + beat registration + model mirror), `frontend-web`
(HubSpot detail page + api client).

**Data model (SQLAlchemy / Alembic).** Add to `HubSpotIntegration` (and its **worker mirror** —
the CI column-parity test requires both):
- `writeback_enabled: bool` (default `False`, server_default false)
- `writeback_field_name: str | None` (nullable; internal HubSpot property name)
- `last_writeback_at: datetime | None`, `last_writeback_status: str | None`,
  `last_writeback_error: str | None`, `contacts_written: int` (default 0)

To make M5 idempotent without an extra HubSpot GET, add to `crm_enrichment` (+ worker mirror):
- `last_written_health_score: int | None`, `last_health_written_at: datetime | None`.
`crm_enrichment` is the correct home because it already holds the `hubspot_contact_id` the PATCH
targets — a customer is writeback-eligible **iff** they have a matched enrichment row.

**Write surface.** New method(s) on the worker `HubSpotClient` (`src/clients/hubspot.py`):
`update_contact_property(contact_id, property_name, value)` → `PATCH /crm/v3/objects/contacts/{id}`,
and `get_property(name)` → `GET /crm/v3/properties/contacts/{name}` for validation. Reuse the
existing Bearer/httpx/transient-error pattern.

**Trigger wiring.** `update_customer_health()` (`health_score_service.py:278`) is called mostly
from the worker but also in-request (CRM disconnect). Enqueue via `celery_app.send_task(name, …)`
so backend need not import worker task modules. Guard the enqueue behind a cheap check (active
HubSpot integration + `writeback_enabled`); do the heavy validation inside the task.

**API (FastAPI).** Extend the HubSpot integration router (`/api/v1/integrations/hubspot`):
- `PATCH /writeback` — body `{ enabled: bool, field_name: str | None }`; validates the field when
  enabling; admin/owner only (mirrors existing route gating).
- `GET /status` — extended with the writeback config + status fields.
- (S1) `POST /writeback/test` — on-demand field validation.

**Multi-tenancy:** all reads/writes scoped by `organization_id`; writeback config is per-org on
the single HubSpot integration row. **BYOK/self-host:** writes use the operator's own private-app
token; no hosted dependency, all unlocked (the `Business+` gating in CLAUDE.md is pre-pivot/stale).

**Non-functional:** respect HubSpot rate limits (batch/backoff on 429); idempotent pushes; the
push task must tolerate a missing `crm_enrichment` row (customer not matched → no-op).

## Risks & Open Questions

- **[confirm at gate] Trigger model** — on-change [default] vs. daily batch beat. On-change fires
  off the primary recompute path (per-feedback analysis), so push frequency tracks analysis
  volume; the ≥2-pt gate + skip-if-unchanged mitigate. Batch is simpler but adds ≤24h lag.
- **[confirm at gate] Field provisioning** — detect/validate [default] vs. auto-create. Auto-create
  is smoother but needs `crm.schemas.contacts.write` and mutates the operator's schema.
- **[confirm at gate] Failure handling** — soft-pause [default] vs. hard-disconnect. Soft-pause
  keeps read-sync alive; chosen to protect G2.
- **Enqueue-from-backend reach:** confirm `backend-api` can `send_task` to the worker broker
  (a Celery app/config is importable there) — else fall back to the daily-batch trigger. *(tech-plan verifies.)*
- **Contact-id freshness:** `hubspot_contact_id` comes from the last inbound sync; a contact
  deleted/merged in HubSpot yields a 404 on PATCH → treat as per-customer skip + status note,
  not a global failure.
- **Worker/backend model parity:** every new column must land on both mirrors or the parity test
  fails — an easy miss.

## Out of Scope

- Salesforce writeback (slice 2) — shape stays provider-generalizable but not built here.
- Multi-field push (churn probability, risk level, drivers), company/account properties.
- Real-time (synchronous/streaming) push; auto-creating HubSpot properties; two-way merge/conflict
  resolution beyond last-writer-wins; simultaneous dual-CRM writeback.
- Any change to inbound sync, health-score math, or plan gating.
