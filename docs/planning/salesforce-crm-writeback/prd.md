# PRD — Salesforce CRM Writeback (health score, slice 2)

**Slug:** `salesforce-crm-writeback` · **Branch:** `feat/salesforce-crm-writeback` · **Type:** feat (freeform)
**Status:** Draft — awaiting review-gate approval
**Date:** 2026-07-05
**Source:** `rereflect-next` recommendation. Deferred-v2 slice named at `AI-TRACKING.md:196` &
`crm-writeback/prd.md:144`. See `../_card/card.md` + `../_card/understanding.md` (4-agent dig).

> All four interview decisions were confirmed by the PM (Contact target, config-on-model,
> persist-id-with-fallback, health-score-only). None are open.

---

## Problem Statement

Rereflect computes a per-customer **health score** (and churn signals), but for **Salesforce**
operators that intelligence never leaves Rereflect. HubSpot orgs already get the loop closed —
health scores flow back to a HubSpot contact property where CSMs run renewals and workflows
(`crm-writeback`, shipped M3.1). Salesforce — the dominant mid-market/enterprise CRM — got only the
**inbound** half (company/ARR/renewal → Customer 360 + health `crm_component`, shipped M3.1b). The
outbound half was explicitly deferred (`AI-TRACKING.md:196` "Salesforce writeback … deferred (v2)";
`crm-writeback/prd.md:49,144` "Salesforce is out of scope … slice 2").

**Evidence it's real:** the asymmetry is documented as a deferred slice in two shipped PRDs, and the
consuming plumbing already exists — a provider-generalized `crm_enrichment` table, a Salesforce OAuth
connection with a **write-capable `api` scope already granted**, a Salesforce REST client, and a
proven HubSpot-writeback blueprint to mirror end-to-end.

**Who has the problem:** the self-hosting operator (CS lead / founder) whose company runs on
Salesforce and wants the Rereflect health score visible inside Salesforce contact views, list
filters, and workflows — without opening Rereflect.

## Goals & Success Metrics

- **G1 — Close the loop for Salesforce.** An opted-in org's matched Salesforce Contacts carry a live
  Rereflect health-score field. *Metric:* for an org with writeback enabled and a valid field
  configured, a Contact with both a `CustomerHealth` row and a resolvable Salesforce Contact Id shows
  a non-stale value in Salesforce, pushed within one trigger cycle of its last score change (≥2-point
  move).
- **G2 — Zero blast radius on the read side.** Enabling/disabling writeback, or a writeback failure,
  never alters inbound enrichment, health scores, or the HubSpot writeback path. *Metric:* the CRM
  read-side characterization tests (`test_crm_provider_generalization.py`) stay **byte-identical**;
  `test_health_writeback_enqueue.py` (HubSpot dispatch) stays green; a forced Salesforce write failure
  leaves read-sync and health recompute green and never flips `is_active`.
- **G3 — Safe by default.** Writeback is **off** until an operator opts in *and* names a validated
  field; pushes are idempotent (no PATCH when the score is unchanged or moved `<2` points).
- **G4 — Legible failures.** A missing/unwritable field, a missing write scope, or a revoked token
  produces a clear **422/400** on the config path (never 500) and a soft-paused status with
  `last_writeback_error` on the push path (never a crash, never `is_active=false`).

**Non-goal for metrics:** no churn-accuracy-lift number is promised (honest-OSS brand).

## User Personas & Scenarios

- **Self-hosting operator / admin (primary).** Has already connected Salesforce (OAuth). In Salesforce
  Setup they create a numeric custom field on Contact (e.g. `Rereflect_Health_Score__c`), enter its
  API name in Rereflect's Salesforce settings, click **Validate**, then flip **writeback on**.
  Rereflect backfills existing matched contacts and thereafter pushes on each score change.
- **CSM (indirect).** Sees the Rereflect health score inside Salesforce Contact records, list views,
  and flow/automation criteria — without logging into Rereflect.
- **Developer (secondary).** Unaffected: the CRM read APIs and `crm_provider` field are unchanged.

## Requirements

### Must-have (slice 2)

- **M1 — One field, one provider, one object.** Push `health_score` (integer 0–100) to **Salesforce**,
  as a **custom field on Contact** (matches the email-based read side). Account-level and multi-field
  push are out of scope.
- **M2 — Opt-in per org, off by default.** New `writeback_enabled` on `SalesforceIntegration` defaults
  `False`; no pushes until an operator enables it *and* a `writeback_field_name` is set.
- **M3 — Validate the operator's field before enabling.** On enable, validate via the Salesforce
  **sObject describe** API (`/services/data/{ver}/sobjects/Contact/describe`) that the field exists,
  is `updateable == true`, and is a numeric type (`double` / `int` / `currency` / `percent`). On
  failure, return **HTTP 400** with `{reason, message}` and leave writeback **disabled**. Enabling
  without a field name → **422**. Reason codes mirror HubSpot semantics:
  `field_not_found` / `missing_write_scope` / `wrong_type` / `validation_error`.
- **M4 — Persist the matched Salesforce Contact Id.** Add `salesforce_contact_id` to `crm_enrichment`
  (+ worker-model mirror + migration) and populate it in the Salesforce sync's `_upsert_enrichment`.
  The push task resolves the target from this column, **falling back to a re-query Contact-by-email**
  when it is null (so writeback works for rows synced before this slice and for backfill-on-enable).
- **M5 — sObject PATCH write path.** Add `update_contact_field(contact_id, field_name, value)` to the
  worker Salesforce client (`PATCH /services/data/{ver}/sobjects/Contact/{id}`, JSON body with the
  **raw number** — not stringified). Add a `describe_object`/field-def helper for M3. Reuse the
  client's `_refresh`, `SalesforceTransientError`/`SalesforceAuthError`, and `_validate_sf_id`.
- **M5a — Deterministic Contact on duplicate email.** Salesforce permits multiple Contacts sharing an
  email (unlike the read-side unique assumption). Both the sync-side persistence (M4) and the
  re-query-by-email fallback must pick **deterministically**: prefer the already-enriched
  `salesforce_contact_id` if present, else the lowest `Id` among matches, and record
  `last_writeback_error="ambiguous_contact"` (soft, non-fatal) when more than one matches on the
  fallback path so the operator can see it. This keeps the score landing on a stable, predictable
  Contact.
- **M6 — Push task with idempotency + soft-pause.** New Celery task
  `src.tasks.salesforce_writeback.push_health_to_salesforce(org_id, customer_email)` mirroring
  `hubspot_writeback.py`: gating no-ops (integration inactive / writeback disabled / no field name /
  no enrichment / no contact id / no health row), **skip-if-unchanged** using the existing provider-
  agnostic `crm_enrichment.last_written_health_score` / `last_health_written_at` (equal → skip;
  `abs(diff) < 2` → skip). On success record `last_written_health_score`, `last_health_written_at`,
  integration `last_writeback_at`/`last_writeback_status="ok"`/`error=None`, and increment
  `contacts_written`. **Soft-pause** on `missing_write_scope` / `field_not_found` /
  `contact_not_found`; **retry** on transient (429/5xx). **Never set `is_active=false`** (owned by
  read-sync). Missing `LLM_ENCRYPTION_KEY` → record `missing_encryption_key`, no retry. Register in
  the worker `celery_app.py` include list.
- **M7 — Generalize the trigger seam.** Extend `_maybe_enqueue_writeback` (`health_score_service.py`)
  so that, in addition to the existing HubSpot dispatch, it also dispatches
  `src.tasks.salesforce_writeback.push_health_to_salesforce` when an active, `writeback_enabled`
  `SalesforceIntegration` exists. Preserve the `abs(new-old) < 2` threshold and the existing-customer-
  only firing. The HubSpot path and `test_health_writeback_enqueue.py` must remain unchanged. (The
  one-CRM-per-org guard means at most one provider is active, so a provider check/dispatch is
  sufficient — no dual push.)
- **M8 — Config + status API.** Under `/api/v1/integrations/salesforce`, add `PATCH /writeback`
  (`{enabled, field_name}` → writeback status fields) and `POST /writeback/test` (`{field_name}` →
  `{ok, reason}`), and surface the writeback fields on `GET /status`. All under
  `require_admin_or_owner` + `require_feature("salesforce_integration")` (the feature gate is an
  unlocked no-op — OSS self-hosted). On successful enable, trigger **backfill** inline.
- **M9 — Backfill on enable.** Mirror HubSpot's inline `_enqueue_backfill_writeback`: enqueue
  `push_health_to_salesforce` for each `crm_enrichment` row for the org with `provider='salesforce'`,
  capped at 500, skipping rows with no resolvable contact id. Never raises.
- **M10 — Frontend writeback card.** New `SalesforceWritebackCard.tsx` mirroring
  `HubSpotWritebackCard.tsx` (Switch enable, field-name Input defaulting to
  `Rereflect_Health_Score__c`, Validate button, status grid, last-error alert; refetch-on-change,
  `null` when disconnected). Extend `lib/api/salesforce.ts` (status writeback fields +
  `updateWriteback` + `testWriteback` + interfaces). Render the card on the Salesforce settings page
  between the connection card and the Help card, gated `status?.connected && isAdminOrOwner`.
- **M11 — Tests (TDD).** RED-first: writeback model columns + migration; describe-based validation
  (each reason code); client PATCH + describe (success + 403/404/429 mapping); push-task matrix
  (gating no-ops, skip-if-unchanged, soft-pause, transient-retry, id-fallback-by-email); trigger
  generalization (Salesforce dispatched; HubSpot unchanged); routes (enable/validate/disable/backfill,
  422/400 paths); the read-side characterization tests stay byte-identical. Frontend `npm run test`
  (card + api) and `npm run lint` green.

### Should-have

- Clear inline error copy on the card for each reason code (reuse HubSpot's `REASON_COPY` /
  `STATUS_COPY` maps, adapted to Salesforce wording).
- Operator setup note (in the Salesforce landing/`SELF_HOSTING.md`) on creating a numeric Contact
  custom field and the `__c` API-name convention — ending with an **end-to-end verification step**:
  "open a Contact in Salesforce and confirm the field is populated." The status card surfaces
  `contacts_written` + `last_writeback_at` as the in-app confirmation signal (matches the repo's
  fix-confirmation ethos).
- **API-limit-aware backfill/push.** Reuse the client's daily-limit backoff
  (`Sforce-Limit-Info`, `DAILY_LIMIT_STOP_THRESHOLD`). When the org is at/over the stop threshold, a
  push records `last_writeback_status="deferred: daily_limit"` and **retries later** (transient-style)
  rather than dropping silently; the 500-cap backfill enqueues individually so limit pressure throttles
  naturally per task rather than in one burst.

### Nice-to-have (explicitly deferred — see Out of Scope)

- Multi-field push (churn probability, risk level, top drivers); Account-object target; operator-
  selectable object; real-time/streaming push.

## Technical Considerations

**Services changed:** `backend-api` (model columns + migration on `salesforce_integrations` and
`crm_enrichment`; new `salesforce_writeback_validation.py`; writeback routes; generalized trigger in
`health_score_service.py`), `worker-service` (new `salesforce_writeback.py` task + `celery_app`
include; new client PATCH/describe methods; `salesforce_sync._upsert_enrichment` persists
`salesforce_contact_id`; `CrmEnrichment` worker-model mirror), `frontend-web` (new card + api client
edits + settings-page render). **No `analysis-engine` change.**

**Auth:** reuse the shipped Salesforce OAuth + `_refresh`; the `api` scope already permits sObject
`PATCH` — **no reconnect required** (`salesforce_integration.py:108`).

**Multi-tenancy:** every endpoint scopes by `organization_id` from JWT; the push task takes `org_id`
+ `customer_email` and re-scopes all lookups; `SalesforceIntegration` and `crm_enrichment` carry
`organization_id`.

**Must-not-regress:** `_compute_crm_component` reads only `renewal_date` (no provider filter) — new
columns must not touch it; the two RED characterization snapshots (`health_score==47`,
`crm_component≈25.0`, the 7 `crm_*` serializer values) stay byte-identical; worker/backend
`CrmEnrichment` column parity is test-asserted — mirror the new column.

### Data Model (changes)

- `salesforce_integrations` (+6 columns, mirror `hubspot_integration.py:38-44`):
  `writeback_enabled` (Bool, default False), `writeback_field_name` (String 255, null),
  `last_writeback_at` (DateTime, null), `last_writeback_status` (String 50, null),
  `last_writeback_error` (Text, null), `contacts_written` (Integer, default 0).
- `crm_enrichment` (+1 column): `salesforce_contact_id` (String 100, null). Reuse existing
  `last_written_health_score` / `last_health_written_at`. Mirror the new column in the worker model.
- One Alembic migration chained off head; worker-model mirror updated in the same slice.

### API Contracts (new, prefix `/api/v1/integrations/salesforce`)

- `PATCH /writeback` — `{enabled: bool, field_name?: str}` → `{writeback_enabled, writeback_field_name,
  last_writeback_at, last_writeback_status, last_writeback_error, contacts_written}`. Enable w/o field
  → 422; validation fail → 400 `{reason, message}` (left disabled); enable success → backfill.
- `POST /writeback/test` — `{field_name: str}` → `{ok: bool, reason?: str}`.
- `GET /status` — extended with the 6 writeback fields.
- All: `require_admin_or_owner` + `require_feature("salesforce_integration")` (no-op unlocked).

## Risks & Open Questions

- **Contact-id coverage on first enable.** Rows synced before this slice have a null
  `salesforce_contact_id`; the push task's re-query-by-email fallback covers them, at the cost of one
  SOQL lookup per such push during backfill. Accepted; daily-limit backoff already exists in the
  client. (Resolved by the persist+fallback decision.)
- **Salesforce field-type set.** Validation accepts `double`/`int`/`currency`/`percent` with
  `updateable==true`; text/formula/read-only fields are rejected as `wrong_type`. Confirmed as the
  slice-2 set; revisit only if an operator needs text.
- **Number formatting.** Salesforce REST expects a JSON number — must NOT copy HubSpot's string
  formatting. Covered by a client test.
- **Trigger double-safety.** The generalized `_maybe_enqueue_writeback` must not double-dispatch or
  change HubSpot behavior; the one-CRM guard makes concurrent providers impossible, but the test
  matrix still asserts HubSpot-only and Salesforce-only cases independently.
- **Backend↔worker model parity.** Adding `salesforce_contact_id` to `crm_enrichment` requires the
  worker mirror + the parity test to stay green.
- **Disconnect resets writeback state.** Disconnect is soft (`is_active=false`) and
  `purge_crm_enrichment(...,'salesforce')` drops the org's Salesforce enrichment rows (incl.
  `salesforce_contact_id` + idempotency memory). Writeback config (`writeback_enabled`,
  `writeback_field_name`) is **reset on disconnect** and must be re-enabled after reconnect, mirroring
  HubSpot; re-enable re-runs backfill. Stated so neither stale config nor silent re-push surprises the
  operator. Covered by a route/lifecycle test.
- **Duplicate-email ambiguity.** See M5a — deterministic pick + `ambiguous_contact` soft error; no
  fan-out write to multiple Contacts in slice 2.

## Out of Scope (deferred to v2)

- **Multi-field push** (churn probability, risk level, top drivers) — health score only.
- **Account-object target** / **operator-selectable object** — Contact only.
- **Real-time / streaming push** (Salesforce Platform Events) — on-change trigger + backfill only.
- **Auto-creating the Salesforce custom field** — operator creates it; we validate.
- **Simultaneous dual-CRM writeback / reconciliation** — precluded by the one-CRM-per-org guard.
- **Salesforce → Rereflect two-way sync of the field.**
