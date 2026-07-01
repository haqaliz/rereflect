# Card — Salesforce CRM Enrichment (freeform)

**Type:** feat · **Slug:** `salesforce-crm-enrichment` · **Branch:** `feat/salesforce-crm-enrichment`
**Source:** Freeform task selected via `rereflect-next` (verified against git — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-01

---

## Brief (from rereflect-next handoff)

Add **Salesforce** as the second CRM enrichment source, reusing the CRM infrastructure the
HubSpot integration already shipped. This is the explicitly-planned next CRM:
`AI-TRACKING.md:23` — "CRM enrichment | **HubSpot first, then Salesforce**" — and an M3.1
follow-on.

### Reuse surface (already shipped by HubSpot, verified present)
- `services/backend-api/src/models/crm_enrichment.py` — per-customer CRM snapshot (currently **HubSpot-shaped**: `hubspot_contact_id`/`company_id`/`deal_id`).
- `services/backend-api/src/services/health_score_service.py` — `_compute_crm_component` (`:108`, used at `:208`); reads **semantic** fields (ARR, renewal, deal stage), so scoring is already provider-agnostic.
- `services/frontend-web/components/customers/CrmCompanyCard.tsx` — CRM card on Customer 360 Overview.
- `crm_*` timeline events on the unified Customer 360 timeline (source-extensible).
- HubSpot precedent to mirror: `src/api/routes/hubspot_integration.py`, the worker HubSpot sync task, `lib/api/hubspot.ts`, HubSpot integrations tile/detail page.

### First-slice shape (proposed — to be pressure-tested in the interview)
1. **Generalize `crm_enrichment`** to be provider-agnostic: add a `provider` discriminator, migrate existing HubSpot rows. Storage side is HubSpot-specific today; scoring/UI consumers are not.
2. **Salesforce connection**: Connected App OAuth 2.0 (connect/disconnect/status/test), instance URL handling, API-version pinning, refresh-token storage (encrypted). Heavier than HubSpot's private-app token.
3. **Salesforce sync**: map Account / Opportunity / Contact → the shared CRM fields (company, ARR, renewal date, deal stage), matched by email. Health component, profile card, and timeline light up for free.

### Fit / guardrails
- OSS self-hosted / BYOK: operator registers their **own** Salesforce Connected App. No hosted dependency, all features unlocked, **no plan gating** (the `Business+` framing in CLAUDE.md/AI-TRACKING is pre-pivot and stale).
- Deepens the churn → health moat (CRM signals into the health score), not just the input layer.

### Known caveat (carry into PRD)
`crm_enrichment` is HubSpot-shaped today, and Salesforce OAuth (instance URLs, API-version
pinning, refresh tokens) is heavier than HubSpot's private-app token. **Do the
generalization migration before wiring the Salesforce adapter**, and preserve byte-for-byte
health-score stability for existing HubSpot-enriched customers (mirror the usage-component
weight-0 discipline: a characterization test proving existing CRM-derived scores are unchanged
after the schema generalization).

### Open questions for the interview
- Generalization strategy: `provider` discriminator on one shared table vs. per-provider columns vs. a normalized `crm_*` field set + provider tag?
- One CRM connected at a time per org, or multiple (HubSpot + Salesforce) simultaneously? If both, how is a customer's CRM row reconciled?
- Salesforce object → field mapping specifics (ARR from Opportunity Amount? renewal date from a custom field / Contract? deal stage from Opportunity StageName?).
- Sync mechanism: polling (mirror HubSpot's Celery beat) vs. Salesforce streaming/Platform Events (likely out of scope for slice 1).
- Auth: full web-server OAuth (redirect URI) vs. JWT bearer flow (server-to-server, no redirect — better fit for headless self-host)?

---

## Reference files (primary repo root)
- `AI-TRACKING.md` — line 23 (CRM strategy: HubSpot then Salesforce), M3.1 (HubSpot, shipped)
- `docs/planning/hubspot-crm-enrichment/` — the HubSpot PRD + aspect specs + plans to mirror
- `memory/rereflect-oss-pivot.md` — OSS/self-hosted/BYOK reality + stale-CLAUDE.md caveat
