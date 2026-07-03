# Card — feat/crm-writeback (freeform)

**Type:** feat · **Slug:** `crm-writeback` · **Branch:** `feat/crm-writeback`
**Source:** Freeform task from `rereflect-next` recommendation (verified against git — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-03

---

## Brief (from rereflect-next handoff)

Build **bi-directional CRM writeback** — the v2 push-back slice deferred on both CRM integrations:
- HubSpot: "Bi-directional sync: push health scores to HubSpot contact properties — **deferred (v2)**" (`AI-TRACKING.md:185`)
- Salesforce: "Bi-directional push-back + simultaneous dual-CRM — **deferred (v2)**" (`AI-TRACKING.md:195`)

Push Rereflect's AI signals (start with `health_score`) back into the connected CRM as a
contact/account property when the health score recomputes, behind an **opt-in per-org
toggle**, reusing the existing provider-agnostic `crm_enrichment` connection + token-refresh layer.

## Scope (slice 1)

- **One field** (`health_score`), **one provider** (HubSpot), **opt-in** per org.
- Push on health-score recompute.
- Graceful handling when the operator has **not** created the custom field or granted write
  scope — surface a clear "grant write scope / create field X" status; do **not** crash the sync.

## Explicitly deferred (later slices)

- Salesforce writeback.
- Multi-field mapping (churn probability, top risk drivers).
- Real-time (vs. batched) push.
- Simultaneous dual-CRM.

## Why (moat / fit)

- Depth-first follow-on of the newest shipped work (HubSpot M3.1, Salesforce M3.1b, shipped 2026-07-01).
- Deepens the "workflow integration" moat pillar; improves as churn/health accuracy improves.
- Fits OSS/self-hosted/BYOK: writes go to the operator's own CRM with their own token —
  no hosted service, no cross-tenant data, all features unlocked (the `Business+` framing in
  CLAUDE.md/AI-TRACKING is pre-pivot and stale).

## Known caveat (carry into PRD)

Writeback needs **write scope + operator-provisioned custom fields** (HubSpot private-app write
scopes; Salesforce field-level security / a custom field per pushed metric), plus write-side
rate-limit backoff and last-writer conflict handling. Keep slice 1 to one field / one provider /
opt-in so scope-and-field provisioning failures degrade to a clear status, not a broken sync.

## Reuse surface (verified present on master in the main-thread dig)

- `services/backend-api/src/models/crm_enrichment.py` — provider-tagged CRM snapshot (`provider` discriminator already shipped for Salesforce).
- HubSpot connection: private-app access token (BYOK) — `src/api/routes/hubspot_integration.py` (or similar).
- Salesforce connection: OAuth 2.0 web-server flow + refresh — `salesforce_integrations` model + routes.
- Sync tasks: daily beat + manual trigger; REST/SOQL clients with token refresh (worker service).
- Health recompute path emits/updates health scores and shares a `crm_component`.
- **No writeback code exists yet** (`grep -riE 'writeback|push.*crm|update_contact_propert' src` → 0 hits).

## Open questions for the interview

- Push trigger: on every health recompute, or debounced/threshold-gated (only when score changes by ≥N)?
- Field-provisioning UX: auto-create the HubSpot custom property via API on connect, or require the operator to create it and just detect/validate presence?
- Which HubSpot object: contact property (per email match) vs. company property? (Slice-1 default: contact, matching the read-side email match.)
- Failure surface: where does "missing write scope / missing field" status live — integration detail page, a new writeback status panel, or per-customer sync log?
- Idempotency/no-op: skip the API call when the CRM property already equals the current score?

---

## Reference files (primary repo root)
- `AI-TRACKING.md` — lines 185 (HubSpot writeback deferred), 195 (Salesforce writeback deferred), 57 (CRM enrichment shipped state).
- `docs/planning/hubspot-crm-enrichment/` — HubSpot PRD + aspect specs + plans (the read-side precedent to mirror the write-side against).
- `docs/planning/salesforce-crm-enrichment/` — provider generalization precedent.
- `memory/rereflect-oss-pivot.md` — OSS/self-hosted/BYOK reality + stale-CLAUDE.md caveat.
