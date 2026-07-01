# PRD — Salesforce CRM Enrichment for Customer 360 + Churn

**Slug:** `salesforce-crm-enrichment`
**Branch:** `feat/salesforce-crm-enrichment`
**Status:** Draft (pre review-gate)
**Author:** Rereflect (via `rereflect-begin-fast`)
**Date:** 2026-07-01
**Roadmap:** `AI-TRACKING.md:23` — "CRM enrichment | HubSpot first, **then Salesforce**"; M3.1 follow-on.
**Source:** Freeform task selected via `rereflect-next` (verified genuinely unbuilt). See `docs/planning/_card/card.md` + `understanding.md`.

---

## Problem Statement

Rereflect's killer feature is "churn prediction that actually works." CRM signals — ARR, deal stage, and especially **contract renewal date** — are among the most predictive external churn indicators. The HubSpot integration already feeds these into the Customer 360 profile, the health score, and the timeline. But **Salesforce is the dominant CRM for the mid-market/enterprise SaaS operators Rereflect targets**, and today a Salesforce-using operator gets none of that enrichment.

The dig (`understanding.md`) shows the consuming layer is *already provider-neutral*: the health component reads only `renewal_date`, the profile serializer exposes only 7 semantic `crm_*` fields, and the frontend `crm_*` fields / timeline events / icons are provider-agnostic. So the cost of the status quo is high (a whole CRM segment unserved) while the marginal cost to serve it is low (mostly additive).

**Who has the problem:** the self-hosted operator (CS lead / founder) whose company runs on Salesforce and who wants health/churn to reflect renewal and account data.

## Goals & Success Metrics

**Goal:** A self-hosted operator connects their Salesforce org and sees Salesforce-sourced company / ARR / renewal / deal data on the Customer 360 profile, folded into the health score (via the existing opt-in CRM weight) and the unified timeline — with zero change to existing HubSpot-enriched orgs.

| Metric | Target |
|---|---|
| Connect → enrich | After connecting Salesforce and one sync cycle, a matched customer's profile shows Salesforce company/ARR/renewal within one Celery run |
| Zero-regression for HubSpot orgs | Adding the `provider` column + generalization leaves every existing HubSpot-enriched customer's `crm_*` API output **and** `crm_component` health score **byte-for-byte identical** (characterization test, RED first) |
| Email match | Salesforce Contacts matched to Rereflect customers by `Contact.Email` (case-insensitive), same machinery as HubSpot |
| Match coverage (measurable) | After the first sync, `status` surfaces `contacts_matched` and a match rate (`contacts_matched / org customer count`) so the operator can gauge value; target is that the number is non-zero and visible, not a fixed % |
| Self-host setup | An operator can connect using a Salesforce Connected App they register themselves — no Rereflect-hosted dependency |
| Provider-correct timeline | CRM timeline events show the actual source ("…from Salesforce"), not a hardcoded "HubSpot" |

**Non-goal for metrics:** no churn-accuracy-lift number is promised in slice 1 (honest-OSS brand).

## User Personas & Scenarios

- **Operator / CS lead (primary):** Registers a Salesforce Connected App, clicks "Connect with Salesforce", completes the OAuth redirect, and Rereflect begins a daily pull. Opens a customer profile and sees the CRM/Company card populated from Salesforce; raises the CRM health weight so upcoming renewals with declining health surface as at-risk.
- **Developer (secondary):** Already consumes the provider-neutral `crm_*` fields on the v1 / public Customer 360 API — those keep working unchanged; a new optional `crm_provider` field tells them the source.

## Decisions locked (interview)

1. **Auth = Web-server OAuth 2.0 redirect**, mirroring the in-repo **Linear** pattern (`getConnectUrl → auth_url → callback`). Store an **encrypted `refresh_token` + `instance_url`**; mint a short-lived access token from the refresh token before each sync. (Chosen over JWT-Bearer and pasted-token; Linear proves redirect OAuth works in this self-hosted product.)
2. **One CRM connected per org at a time.** Connecting Salesforce while HubSpot is active (or vice-versa) is **blocked with a clear message** ("disconnect X first"). A `provider` column tags `crm_enrichment` rows; no cross-provider reconciliation in slice 1. Keeps `crm_enrichment`'s `(org, email)` uniqueness valid.
3. **Pull-only** enrichment (read Salesforce → enrich Rereflect). No push-back of health scores to Salesforce.
4. **Separate `salesforce_integrations` table** (mirrors `hubspot_integrations`, zero constraint changes) rather than a unified `crm_integrations` table.
5. **Field mapping:** `company_name ← Account.Name`, `arr ← Account.AnnualRevenue`, `lifecycle_stage ← Account.Type` (or null), `deal_name ← Opportunity.Name`, `deal_stage ← Opportunity.StageName`, `deal_amount ← Opportunity.Amount`, `renewal_date ← CloseDate of the picked open renewal Opportunity`. Renewal pick mirrors HubSpot's `_pick_renewal_deal` (open stage, has close date, highest amount). Match by `Contact.Email`; `Contact.AccountId` is a direct FK (no associations round-trip).
6. **Sync:** daily Celery beat (new UTC slot, e.g. 03:45) + manual trigger endpoint; polling, pull-only.
7. **Disconnect purges** that provider's `crm_enrichment` rows for the org + recomputes affected health scores (shared helper, applied to both Salesforce and HubSpot disconnect for consistency).

## Requirements

### Must-have (slice 1)

1. **Provider generalization (foundation).** Add `provider VARCHAR(50) NOT NULL DEFAULT 'hubspot'` to `crm_enrichment` (backend model + worker mirror + migration chained off head `d4e5f6a7b8c9`). Make `customer_timeline_service._fetch_crm_events` emit `source=row.provider` and provider-correct descriptions instead of the hardcoded `"hubspot"` / "from HubSpot". Surface an optional `crm_provider` on the shared serializer + v1 + public profile responses (kept in parity). **No change to `_compute_crm_component` or the weights.**
2. **Score-stability characterization test (RED first).** Assert that, for a fixture HubSpot-enriched org, the serialized `crm_*` profile fields and `compute_health_score()` output are identical before/after the generalization. Written RED in the generalization aspect before the column exists.
3. **Salesforce connection (OAuth).** `salesforce_integrations` model + migration (encrypted `refresh_token`, `instance_url`, `sf_org_id`, `token_hint`, status/sync-stat columns, `UniqueConstraint(organization_id)`). Endpoints under `/api/v1/integrations/salesforce`: `GET /connect-url`, `GET/POST /callback` (OAuth code exchange), `GET /status`, `DELETE /disconnect`, `POST /test`, `POST /sync` (manual trigger → `send_task`). `require_admin_or_owner` + `require_feature("salesforce_integration")`. Reuse `src/utils/encryption.py` + R6 guard (→ 422, never 500). **One-CRM guard must be symmetric:** a shared helper (`another_crm_active(org, exclude=<provider>)`) is enforced on **both** the Salesforce connect path **and** the HubSpot connect path (add the check to `hubspot_integration.py` connect too) so the collision cannot be created from either direction — this is what makes decision D3 actually hold.
4. **Salesforce sync (worker).** `clients/salesforce.py`: token refresh from `refresh_token`, SOQL over the REST Query API (`/services/data/vXX.X/query`), `nextRecordsUrl` pagination, daily-limit-aware backoff (`Sforce-Limit-Info`), a `SalesforceTransientError` for retryable 429/5xx. `tasks/salesforce_sync.py`: `_sync_org` upserts `CrmEnrichment` with `provider='salesforce'`, renewal-opportunity pick, `_call_update_health` recompute; `sync_all_salesforce` fan-out + retryable `sync_salesforce_org`; register in `celery_app.py` include + a new beat entry.
5. **Frontend.** `lib/api/salesforce.ts` (Linear OAuth shape: `getConnectUrl`, `getStatus`, `disconnect`, `test`); a Salesforce tile on the integrations index (Salesforce-blue brand); `settings/integrations/salesforce/page.tsx` with an OAuth "Connect with Salesforce" CTA (mirror `linear/page.tsx:339-350`), connected-state grid + Test/Disconnect (mirror HubSpot page), RBAC member-redirect guard. Provider-neutral copy fix in `CrmCompanyCard.tsx:50`.
6. **Graceful degradation.** No Salesforce connected ⇒ nothing changes anywhere. Missing `LLM_ENCRYPTION_KEY` ⇒ 422 with an operator-actionable message. Sync failures set `last_sync_status`/`last_error`, never crash the health path.

### Should-have
- `crm_provider` badge on the CRM/Company card (show which CRM populated it).
- A dedicated `SalesforceIcon.tsx` (mirror `LinearIcon.tsx`) instead of a monogram.
- Operator docs in `docs/SELF_HOSTING.md`: how to register a Connected App, scopes (`refresh_token offline_access api`), redirect URI, and a "verify it's working" note.

### Nice-to-have (explicit v2)
- Bi-directional push-back (health scores → Salesforce custom fields).
- Both CRMs connected simultaneously with per-customer reconciliation.
- Salesforce Platform Events / streaming (vs polling).
- Configurable SOQL field mapping per org.
- Salesforce Bulk API for very large orgs.

## Technical Considerations

**Services touched:** `backend-api` (route, models, migration, serializer/timeline generalization, plans), `worker-service` (client, task, model mirrors, beat), `frontend-web` (api client, tile, connect page, icon, copy). `analysis-engine` unaffected.

**Multi-tenancy:** every row carries `organization_id`; the Connected App credentials resolve the org. `crm_enrichment` matching stays `(organization_id, customer_email)`; `provider` tags the source. No cross-tenant path.

**Alembic:** head is `d4e5f6a7b8c9`. The generalization migration (provider column) and the `salesforce_integrations` migration chain linearly off it (integrator supplies revision ids between aspects).

**Worker model parity:** a CI test enforces `CrmEnrichment` column parity between backend and worker — the `provider` column must be added to **both** `src/models/crm_enrichment.py` and `worker-service/src/models/__init__.py`.

**Reuse (from dig):** encryption `src/utils/encryption.py`; OAuth precedent `linear_integration.py` + `linear.ts` + `linear/page.tsx`; sync structure `worker-service/src/tasks/hubspot_sync.py` + `clients/hubspot.py`; health recompute `update_customer_health` (`health_score_service.py:278`); serializer `customer_profile_serializer.py:91-130`; timeline `customer_timeline_service.py:435-491`.

## Risks & Open Questions

- **Salesforce OAuth friction in self-host (top risk, surfaced in interview):** redirect OAuth needs a reachable callback URL + a Connected App the operator registers. Mitigated by mirroring the working Linear flow and documenting Connected App setup; JWT-Bearer remains a v2 fallback if operators push back.
- **Access-token refresh lifecycle:** Salesforce access tokens are short-lived; the client must refresh before each sync and handle `invalid_grant` (revoked refresh token) by marking the integration disconnected with a clear error.
- **Score-stability regression:** adding `provider` must not shift existing scores — mitigated by `server_default='hubspot'` + the RED characterization test.
- **API limits on large orgs:** SOQL over the Query API with a per-run page cap (mirror HubSpot's `PER_RUN_PAGE_CAP`); Bulk API deferred to v2. Log when the cap is hit.
- **Resolved (gate) — stale enrichment rows on disconnect → PURGE.** Decision **(a)**: disconnecting a CRM deletes that provider's `crm_enrichment` rows for the org and recomputes the affected customers' health scores (so a disconnected CRM never silently influences scores). Implemented via a shared helper used by the Salesforce disconnect (and applied to HubSpot disconnect too, for consistency). See locked decision 7.
- **Open:** exact Salesforce API version to pin (e.g. `v60.0`) — finalize in the connection spec.
- **Open:** `renewal_date` source when an org tracks renewals via Contracts rather than Opportunities — slice 1 uses Opportunity `CloseDate`; document the limitation.

## Out of Scope
- Bi-directional push-back to Salesforce (v2).
- Two CRMs active at once + reconciliation (v2).
- Streaming/Platform Events; Bulk API.
- Any plan-tier gating — OSS self-hosted, all features unlocked (the `Business+` framing in CLAUDE.md/AI-TRACKING is pre-pivot and stale).
- Renaming existing HubSpot modules/routes/pages — Salesforce is an additive sibling.
