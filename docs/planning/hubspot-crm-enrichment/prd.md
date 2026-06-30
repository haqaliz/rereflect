# PRD — HubSpot CRM Enrichment for Customer 360 + Churn

**Slug:** `hubspot-crm-enrichment`
**Branch:** `feat/hubspot-crm-enrichment`
**Status:** Draft (pre review-gate)
**Author:** Rereflect (via `rereflect-begin-fast`)
**Source:** Freeform task — see `docs/planning/_card/card.md` + `understanding.md`.
Selected by `rereflect-next` as the highest-leverage next feature.

---

## Problem Statement

Rereflect's killer feature is "churn prediction that actually works"
(`AI-TRACKING.md:5`). Today the health/churn signal is built only from
**Rereflect-native** data (feedback sentiment, resolution, frequency, and — since
M3.2 — product usage). It is blind to the single most predictive external churn
signal a B2B SaaS operator has: **the commercial relationship** — ARR/MRR, the
contract **renewal date**, and the **deal stage / lifecycle stage** that live in
their CRM.

HubSpot CRM enrichment is the last open data-enrichment source on the roadmap
(`AI-TRACKING.md` M3.1, lines 178–186; `DEV-TRACKING.md` M3.5, lines 209–213 — all
unchecked). It is also the explicit unblocker for the one piece deferred in the
just-shipped unified Customer 360 timeline: "CRM events **deferred** until HubSpot
(M3.1)" (`AI-TRACKING.md:204`).

**Who has this problem:** self-hosting operators (CS leads, founders, PMs) running
Rereflect against their own data and their own HubSpot portal. They can see a
customer's sentiment and usage decline but cannot see that the same customer has a
$120k renewal in 21 days — exactly when intervention matters most.

**Evidence it's real:** the roadmap's churn-enrichment rule is stated verbatim —
"renewal coming up + declining health = critical" (`AI-TRACKING.md:183`) — and the
timeline service was deliberately built source-extensible to accept CRM events
later (`customer_timeline_service.py` `build_timeline`).

## Goals & Success Metrics

**Goal:** An operator pastes a HubSpot private-app token, and within one sync their
Rereflect customers show company / ARR / renewal date / deal stage on the Customer
360 profile, those facts appear on the unified timeline, and (opt-in) they move the
health/churn score.

| Metric | Target |
|--------|--------|
| Connect → first enrichment visible | ≤ 1 manual "Sync now" (seconds), no redeploy |
| Customers matched | All HubSpot contacts whose email matches a Rereflect `customer_email`, by exact lowercased email |
| Health-score impact | Zero by default (0% weight); only when operator sets `health_weight_crm > 0` |
| Sync resilience | One org's HubSpot failure never aborts the batch; transient HTTP failures retried |
| Test coverage | Every new core function + route under strict TDD (RED→GREEN→REFACTOR) |
| Qualitative value (no telemetry in OSS) | On a connected portal, the at-risk list and a customer's timeline visibly surface an imminent renewal that sentiment/usage alone did not — verifiable by the operator |

**Non-metrics (honesty):** we do **not** claim improved churn AUC in v1 — the
calibrated heuristic is unchanged unless the operator opts the CRM component in.
No fabricated accuracy numbers.

## User Personas & Scenarios

- **CS lead (admin/owner):** connects HubSpot in Settings → Integrations, pastes a
  private-app token, clicks "Sync now", sees a connected status with last-synced
  time and matched-contact count.
- **CS lead viewing a customer:** opens `/customers/{email}`, sees a new
  **CRM / Company** card (company, lifecycle stage, ARR, renewal date, open deal +
  stage) and CRM events interleaved in the Full Activity Timeline.
- **Operator tuning churn:** in health-score weight settings, raises
  `health_weight_crm` from 0 so an imminent renewal on a declining account pushes
  the customer toward "at-risk".

## Requirements

### Must-have (v1)

1. **Connect via private-app token (BYOK).** Org-admin pastes a HubSpot private-app
   access token; stored **Fernet-encrypted** (`encrypt_api_key`). Connect /
   disconnect / status / **test connection**. One connection per org.
2. **Sync Contacts + Companies + Deals.** Pull contacts (email, lifecycle stage,
   company association), their associated company (name, ARR/MRR property), and
   associated open deal(s) (amount, stage, close/renewal date). Match contacts to
   Rereflect customers by exact lowercased `customer_email`.
3. **Per-customer enrichment store.** New `crm_enrichment` table keyed
   `(organization_id, customer_email)` (mirrors `CustomerUsage`), holding the
   resolved company name, lifecycle stage, ARR, renewal/close date, primary deal
   name + stage + amount, `hubspot_contact_id`/`company_id`/`deal_id`, and
   `last_synced_at`.
4. **Manual "Sync now" + daily scheduled sync.** A POST endpoint enqueues an
   immediate per-org sync; a Celery beat task syncs all connected orgs daily
   (new entry alongside `sync-integrations-daily` 02:00 / `recompute-usage-scores` 04:00).
5. **Customer 360 profile card.** A `CrmCompanyCard` on the profile Overview tab
   (mirrors `UsageActivityCard`); CRM fields added to `serialize_customer_profile`
   so both the v1 route and the public profile pick them up automatically.
6. **Opt-in weighted health component.** New `crm_component` on `CustomerHealth` +
   `CustomerHealthHistory`, `_compute_crm_component` (SAVEPOINT / never-raise,
   neutral 50 on no data), `OrgAIConfig.health_weight_crm` (default 0), wired into
   `_get_org_weights` + the weighted sum. The component encodes the
   "renewal-soon + low base → lower component" intuition; default 0% = no behavior
   change until opted in.
7. **CRM timeline events (minimal set).** `_fetch_crm_events` emitting the events
   **derivable from the current enrichment snapshot** — `crm_contact_synced`
   (at `last_synced_at`) and `crm_renewal_upcoming` (when `renewal_date` is within
   the window) — merged into `build_timeline`; new `Optional` payload fields on
   `TimelineEvent` + `ActivityEvent`; matching `eventIconMap` entries in the
   frontend. `crm_deal_stage_changed` requires change-tracking across syncs and is
   **deferred to v2** unless cheap (a single snapshot can't detect a change — see R6).
8. **RBAC + multi-tenancy.** All management routes gated by `require_admin_or_owner`
   (+ a no-op `require_feature("hubspot_integration")` registered for future-
   proofing); every query scoped by `organization_id`.
9. **Self-hosted fit.** No plan gating enforced (all unlocked); token is the
   operator's own; no central/cross-customer data. No new required env var beyond
   the existing `LLM_ENCRYPTION_KEY` (reused for token encryption).

### Should-have

- Sync summary surfaced in status (contacts pulled, matched, skipped, last error).
- Rate-limit-aware client (respect HubSpot 429 + `Retry-After`; paginate).
- Backfill: a freshly raised `health_weight_crm` recomputes affected customers'
  scores on next sync / recompute.

### Nice-to-have (out of v1 unless cheap)

- "Renewal upcoming" surfaced as a dashboard at-risk reason.
- Configurable which HubSpot property maps to ARR (operator's portal may use a
  custom property name).

## Technical Considerations

**Services changed:** backend-api (models, routes, health service, profile
serializer, timeline service, Alembic migration), worker-service (sync task, beat,
mirror model, HubSpot client), frontend-web (api client, settings UI, profile card,
timeline icons). analysis-engine: unchanged.

**Key precedents to mirror (from `understanding.md`):**
- Connection model → `LinearIntegration` (one row/org); token encryption →
  `webhooks.py` / `ai_settings.py` (`encrypt_api_key`), **not** Linear (which stores
  plaintext — a known gotcha, do not copy).
- Health component → the shipped `usage_component` + configurable weights (M4.2).
- Profile fields → `customer_profile_serializer.py` (single source for v1 +
  public).
- Timeline → `_fetch_churn_events` / `_derive_notable_usage_events` + `eventIconMap`.
- Worker sync → `integrations.py:sync_all_integrations` fan-out + `usage_metrics`
  upsert/health-recompute shape; decorate every task `@shared_task(name=...)`
  (the bare-`def` churn_calibration beat tasks are an anti-pattern).

**Data model (new):**
- `hubspot_integrations` — one row/org: `organization_id` (unique), `access_token`
  (encrypted), `hub_id`/`portal_name`, `connected_by_user_id`, `connected_at`,
  `is_active`, `last_synced_at`, `last_sync_status`, `last_error`, counts.
- `crm_enrichment` — `(organization_id, customer_email)` unique: `company_name`,
  `lifecycle_stage`, `arr`, `renewal_date`, `deal_name`, `deal_stage`,
  `deal_amount`, `hubspot_contact_id`, `hubspot_company_id`, `hubspot_deal_id`,
  `last_synced_at`.
- New columns: `customer_health_scores.crm_component`,
  `customer_health_history.crm_component`, `org_ai_config.health_weight_crm`.
- One Alembic migration in backend-api off current head; mirror tables (no FK) added
  to the worker's `src/models/__init__.py`.

**Multi-tenancy:** connection + enrichment + all queries keyed/filtered by
`organization_id`. The HubSpot token is per-org.

**Migration implications:** all additive (new tables + nullable columns +
`health_weight_crm` default 0). No backfill required for safety; existing scores
unchanged because default weight is 0.

## Risks & Open Questions

- **R1 — Object graph complexity.** Contact→Company→Deal associations and which
  deal counts as "the renewal" are fuzzy. *Mitigation:* v1 picks the
  highest-value open deal with a close date as the renewal proxy; document the
  heuristic honestly; make the ARR property name a should-have config.
- **R2 — HubSpot rate limits / pagination.** Large portals exceed page sizes and
  hit 429s. *Mitigation:* paginate, honor `Retry-After`, Celery retry; cap per-run
  work and log truncation (no silent caps).
- **R3 — Token security.** Must encrypt at rest (do **not** repeat Linear's
  plaintext mistake) and never return the token to the client (status shows a hint
  only).
- **R4 — Worker/backend model drift.** The CRM table + `health_weight_crm` must be
  mirrored in the worker models; the worker's `OrgAIConfig` mirror currently lacks
  even `health_weight_usage`. *Mitigation:* add `health_weight_crm` to the worker
  mirror, or keep weight-reading solely in backend-api and have the worker only
  trigger a recompute (decide in tech-plan).
- **R5 — Email match quality.** Same caveats as usage matching (case, aliases).
  *Mitigation:* reuse the exact lowercased-email match used by usage; report
  unmatched count.
- **R6 — `LLM_ENCRYPTION_KEY` hard dependency.** Token encryption reuses
  `encrypt_api_key`, which **raises `ValueError` if `LLM_ENCRYPTION_KEY` is unset**.
  A self-hoster running only a local/keyless LLM may never have set it, so
  `POST /connect` would 500. *Mitigation:* the connect route must detect a missing
  key and return a clear, actionable 4xx ("set `LLM_ENCRYPTION_KEY` to connect a
  CRM"), document it in the integration UI + README, and a test must cover the
  missing-key path. (This is the headline GTM/feasibility gap from self-critique.)
- **R7 — Heuristic validity.** Lowering health for a near renewal could wrongly
  flag a healthy, likely-to-renew account. *Mitigation:* the component is **opt-in
  (0% default)**, deterministic, and documented as a heuristic — not a trained
  model; no accuracy claims. Operators tune the weight to taste.

**Resolved (interview):** objects = Contacts+Companies+Deals; health = opt-in
weighted `crm_component` (default 0%); trigger = manual + daily; timeline = minimal
CRM event set. Data model = separate `crm_enrichment` table; gating =
`require_admin_or_owner` + no-op feature id; public API = serializer auto-flow.

## Out of Scope (v1)

- **OAuth marketplace app / install flow** — private-app token only. (v2)
- **Bi-directional sync** — pushing Rereflect health scores back to HubSpot custom
  properties. (v2)
- **Salesforce or any other CRM** — HubSpot only.
- **Real-time HubSpot webhooks** — pull-only (manual + daily). (v2)
- **A dedicated public API endpoint for CRM** — fields ride the existing profile
  serializer; no new `/api/public/v1` route.
- **Custom per-org field mapping UI** beyond an optional ARR property name.
- **Renewal-proximity hard modifier** on the score — we use the opt-in weighted
  component instead.
- **Claiming improved churn accuracy** — no benchmark/metric claims in v1.

## Aspects (decomposition follows)

1. `hubspot-connection` — model, encryption, connect/disconnect/status/test routes,
   settings UI.
2. `hubspot-sync` — worker HubSpot client, sync task (fan-out + per-org), beat
   entry, `crm_enrichment` upsert, manual "Sync now" endpoint.
3. `crm-health-component` — `crm_component` column/history, `_compute_crm_component`,
   `health_weight_crm`, weighted-sum wiring.
4. `crm-profile-and-timeline` — serializer fields, `CrmCompanyCard`, `_fetch_crm_events`
   + timeline payload fields + `eventIconMap`.
