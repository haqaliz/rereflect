# Understanding — HubSpot CRM Enrichment

Synthesis of the Phase 2 deep dig (backend / worker / frontend code maps). All
paths relative to each service under `services/` in this worktree.

## What the feature is really asking

Let a self-hoster connect **their own** HubSpot portal (single-tenant, BYOK-style)
so that Rereflect customers — identified by `(organization_id, customer_email)` —
are enriched with CRM facts (company, ARR / deal value, renewal date, deal stage,
lifecycle stage), those facts (a) show on the Customer 360 profile, (b) appear as
events on the unified timeline, and (c) feed a renewal/ARR signal into the
health/churn score. First slice = **private-app access token + pull-only sync**;
OAuth marketplace app and bi-directional push-back are explicit v2.

## Architecture reality (important, overrides CLAUDE.md)

- **No `customers` table.** A customer is the `(organization_id, customer_email)`
  pair, materialized in `customer_health_scores` (`CustomerHealth`). Enrichment
  must key on that pair, exactly like `CustomerUsage` (M3.2) does.
- **Worker has its own mirror models** (`worker-service/src/models/__init__.py`,
  no FK constraints) separate from backend-api's SQLAlchemy models. A new
  enrichment table must be declared in **both** places; the **real Alembic
  migration lives in backend-api** (`services/backend-api/alembic/`).
- **`health_score_service.py` exists only in backend-api.** The worker calls
  `update_customer_health(...)` via a guarded lazy import that tolerates
  `ImportError` — so the worker sync triggers a recompute best-effort.
- **Plan gating is stale (OSS pivot).** `require_feature(...)` still exists but
  every feature is unlocked self-hosted. See open question OQ-2 on gating.

## The five injection points (all have a close, shipped precedent)

| # | Area | New work | Mirror this precedent |
|---|------|----------|----------------------|
| 1 | **Model + token storage** | `HubSpotIntegration` (one row/org, `UniqueConstraint(organization_id)`), token stored **Fernet-encrypted**. Optional `customer_email → hubspot_*` mapping/enrichment table keyed `(org, email)`. | `linear_integration.py` (shape) + `webhooks.py`/`ai_settings.py` encryption (`encrypt_api_key`/`decrypt_api_key`, `src/utils/encryption.py`, key = `LLM_ENCRYPTION_KEY`) |
| 2 | **Management routes** | `/api/v1/integrations/hubspot` connect / disconnect / status / test (+ sync trigger). Register in `src/api/main.py`. Gate with `require_admin_or_owner` (see OQ-2). | `src/api/routes/linear_integration.py` (lifecycle), `integrations.py` (token-in-body create) |
| 3 | **Health score component** | Add opt-in `crm_component` (default 0% weight) → column on `CustomerHealth` + `CustomerHealthHistory`, `_compute_crm_component` (SAVEPOINT / never-raise), `OrgAIConfig.health_weight_crm`, add to `_get_org_weights` + weighted sum. | `_compute_usage_component` + the M4.2 usage-component / configurable-weights work (`tests/test_health_usage_component.py`, `test_health_weights.py`) |
| 4 | **Customer 360 profile** | Add CRM fields to `serialize_customer_profile` → flows to **both** the v1 route and the public API automatically. New `CrmCompanyCard` on the profile Overview tab. | `customer_profile_serializer.py`; frontend `UsageActivityCard` |
| 5 | **Timeline** | `_fetch_crm_events(...)` returning `TimelineEvent`s with new `crm_*` types + one `extend()` in `build_timeline`; add `Optional` payload fields to `TimelineEvent` (backend) + `ActivityEvent` (`customers.py`) + `eventIconMap` (frontend). | `_fetch_churn_events` / `_derive_notable_usage_events`; `eventIconMap` in `ActivityTimeline.tsx` |

## Worker sync shape

- New `src/tasks/hubspot_sync.py`: Celery-free core + `@shared_task(name=...)`
  fan-out (`sync_all_hubspot` iterates orgs with an active HubSpot integration →
  per-org `sync_hubspot_org.delay()`), mirroring `integrations.py:sync_all_integrations`
  (the existing `sync-integrations-daily` 02:00 UTC beat entry is the precedent).
- **Must** be added to `celery_app.py` `include=[...]` (no autodiscovery) and a
  `beat_schedule` crontab entry.
- HubSpot REST client via `httpx.Client` with `Authorization: Bearer <decrypted token>`,
  broad try/except + log, Celery `self.retry` for transient failures (mirror
  `adapters/intercom.py` + `webhook_delivery.py`).
- Upsert keyed `(org, email)` Python-level (no PG `ON CONFLICT`, for SQLite tests),
  then guarded `update_customer_health(org, email, db)` call.

## Contradictions / gotchas to carry into PRD + plan

1. **Linear stores its OAuth token in plaintext** (`linear_integration.py:412/425`)
   despite a "Fernet-encrypted" comment. Do **not** copy that — HubSpot token must
   actually be encrypted (webhooks/BYOK pattern).
2. **Linear/Slack routes gate only on `require_feature`, not `require_admin_or_owner`**,
   contradicting CLAUDE.md's "Manage integrations = admin/owner" matrix. HubSpot
   should add `require_admin_or_owner` explicitly. → OQ-2.
3. **`churn_calibration.py` beat tasks are bare `def`s** (no `@shared_task`) and are
   likely silently unregistered. Don't copy; always decorate.
4. **Worker mirror `OrgAIConfig` lacks `health_weight_usage`** today; if we add
   `health_weight_crm` the worker mirror needs it too (or the worker stays
   best-effort and only backend-api reads the weight).
5. Tests use **in-memory SQLite, no Celery eager mode** — logic must live in a
   plain core function tested directly; external HTTP mocked.

## Open questions for the requirements interview

- **OQ-1 Data model:** single `HubSpotIntegration` row/org for the connection, plus
  a separate per-customer enrichment table (`crm_enrichment` keyed `(org, email)`)
  vs. columns on `CustomerHealth`? (Lean: separate table — mirrors `CustomerUsage`.)
- **OQ-2 Auth/RBAC gating under OSS:** plan gating is unlocked; do we keep a
  `require_feature("hubspot_integration")` (no-op self-hosted but future-proof) and
  add `require_admin_or_owner`, or just `require_admin_or_owner`?
- **OQ-3 Sync trigger:** on-demand only, scheduled (daily, like usage/integrations),
  or both (manual "Sync now" + daily beat)?
- **OQ-4 Health integration:** new opt-in weighted `crm_component` (default 0%) vs.
  a renewal-proximity modifier applied post-sum? Either changes the churn signal —
  confirm which, and the exact "renewal soon + declining = critical" rule.
- **OQ-5 Which HubSpot objects in v1:** Contacts only, or Contacts + Companies +
  Deals? (Renewal date / ARR typically live on Company or Deal, not Contact —
  affects the API calls and the matching join.)
- **OQ-6 Timeline CRM event types** to emit in v1 (e.g. `crm_deal_stage_changed`,
  `crm_renewal_upcoming`) — or defer timeline events to a later sub-slice and ship
  connect + profile-card + health first?
- **OQ-7 Public API exposure:** confirm CRM fields flow into the public profile
  serializer automatically (no new public endpoint) — acceptable, or hold CRM out
  of the public serializer in v1?

## Affected areas (file-level)

- **backend-api:** `src/models/` (+ HubSpotIntegration, enrichment table, CRM columns),
  `src/api/routes/hubspot_integration.py` (new) + `main.py`, `src/services/health_score_service.py`,
  `src/services/customer_profile_serializer.py`, `src/services/customer_timeline_service.py`,
  `src/api/routes/customers.py` (ActivityEvent/profile schema), `src/utils/encryption.py` (reuse),
  `src/config/plans.py` (feature id, if OQ-2 keeps it), `alembic/` (migration), `tests/`.
- **worker-service:** `src/tasks/hubspot_sync.py` (new), `src/celery_app.py` (include + beat),
  `src/models/__init__.py` (mirror table + maybe weight col), a new `src/clients/hubspot.py` or
  `src/adapters/hubspot.py`, `tests/`.
- **frontend-web:** `lib/api/hubspot.ts` (new), `app/(dashboard)/settings/integrations/page.tsx`
  (+ tile + status fetch), `app/(dashboard)/settings/integrations/hubspot/page.tsx` (new),
  `lib/api/customers.ts` (ActivityEvent union + CRM fields), `components/customers/ActivityTimeline.tsx`
  (eventIconMap), new `CrmCompanyCard` on `app/(dashboard)/customers/[email]/page.tsx`, `__tests__/`.
