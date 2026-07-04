# Card: feat/salesforce-crm-writeback (freeform)

**Type:** feat · **Slug:** `salesforce-crm-writeback` · **Branch:** `feat/salesforce-crm-writeback`
**Source:** Freeform task from the `rereflect-next` recommendation handoff (verified against git — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-05

---

## Brief (verbatim from handoff)

Build **slice 2 of CRM writeback: push the Rereflect health score back to Salesforce**, mirroring
the shipped HubSpot writeback (`docs/planning/crm-writeback/`) and consuming the already-shipped
Salesforce OAuth connection + client from `salesforce-crm-enrichment`. First generalize the
writeback config/trigger (today HubSpot-model-specific per `crm-writeback/prd.md` M2) to a provider
dimension, then add the Salesforce sObject `PATCH` write path targeting an operator-configured
writable field on Account/Contact — validate the field exists and is writable (422, never 500;
soft-pause on missing scope), keep writeback off-by-default and idempotent, and hold the CRM
read-side characterization tests byte-identical (crm-writeback G2). Fits OSS/self-hosted/BYOK
(operator's own Connected App, all unlocked); one-CRM-per-org already rules out dual-provider
writeback, so no reconciliation needed in this slice.

## Provenance / roadmap references

- `AI-TRACKING.md:196` — "Bi-directional push-back (HubSpot shipped in M3.1; **Salesforce writeback**)
  + simultaneous dual-CRM — **deferred (v2)**". This slice builds the Salesforce half.
- `docs/planning/crm-writeback/prd.md:144` — "**Salesforce writeback (slice 2)** — shape stays
  provider-generalizable but not built here." Names this exact follow-on.
- `docs/planning/crm-writeback/prd.md:49,81` — HubSpot writeback slice 1 explicitly scopes
  "Salesforce is out of scope" and lists it as a deferred nice-to-have.
- `AI-TRACKING.md:186,189-197` — HubSpot writeback (M3.1) and Salesforce inbound enrichment (M3.1b,
  COMPLETE 2026-07-01) both shipped; git commits `5e2943d`/`10f4640`/`688f788`/`b45f489` (HubSpot
  writeback) and `~309c37c..47a3733` (Salesforce enrichment).
- Guardrail: OSS self-hosted, MIT, BYOK — all features unlocked, **no plan gating** (the
  `Pro+`/`Business+` framing in CLAUDE.md / AI-TRACKING is pre-pivot and stale).

## Scope (slice 2 — Salesforce writeback)

- **Generalize the writeback config + trigger** from HubSpot-model-specific to a provider dimension
  so the same on-change/backfill push machinery serves either CRM. (Slice 1 put config on
  `HubSpotIntegration` mirroring `arr_property_name`.)
- **Salesforce write path**: `PATCH` the health score to an operator-configured writable field on the
  matched Salesforce **Contact** (email-matched, like the read side) or Account, via the REST
  sObject update API, reusing the shipped Salesforce client's token-refresh.
- **Field validation + soft-pause**: validate the target field exists and is writable up front; on
  missing write scope / missing field, return **422 (never 500)** and soft-pause writeback with a
  `last_error`, mirroring HubSpot's slice-1 behavior.
- **Off by default, idempotent**: no push until the operator opts in and names a field; skip
  redundant writes when the value is unchanged.
- **Zero read-side blast radius**: the CRM read-side characterization tests
  (`test_crm_provider_generalization.py`) must stay byte-identical (crm-writeback G2).
- **Frontend**: a Salesforce writeback card on the Salesforce integration settings page mirroring the
  shipped HubSpot writeback toggle/field/validate/status card.

## Explicitly deferred (later slices / v2)

- **Multi-field push** (churn probability, risk level, top drivers) — health score only in this slice
  (mirrors HubSpot slice-1 single-field scope, `crm-writeback/prd.md:48`).
- **Simultaneous dual-CRM writeback / reconciliation** — one-CRM-per-org guard (M3.1b) makes this
  moot for now (`AI-TRACKING.md:196`).
- **Real-time / streaming push** (Salesforce Platform Events) — on-change trigger + backfill only.
- **Auto-creating the Salesforce custom field** — operator creates it themselves (BYOK), we validate.

## Why (moat / fit)

- Completes the **churn → health → CRM system-of-record** loop for Salesforce orgs, the dominant
  mid-market/enterprise CRM — directly serving the product's killer feature ("churn prediction that
  actually works"; `AI-TRACKING.md:5`).
- **Unblocked, depth-first, follow-on of shipped work**: the on-change writeback trigger + config +
  UI shipped for HubSpot; the Salesforce OAuth connection + client (token refresh, sObject access)
  shipped for enrichment; the `crm_enrichment` layer is already provider-generalized. This slice is
  mostly additive.
- Closes a real **symmetry gap** (HubSpot has writeback, Salesforce doesn't) and fits
  OSS/self-hosted/BYOK — the operator owns their Connected App and the target field, all unlocked.

## Known caveat (carry into PRD)

The writeback **config + trigger currently live on `HubSpotIntegration`** (`crm-writeback/prd.md`
M2, mirroring `arr_property_name`) — not yet provider-generalized. So slice 2 must **first lift the
writeback config/trigger to a provider dimension**, then add the Salesforce sObject `PATCH` write
path. Salesforce writeback also needs the operator's **Connected App OAuth scope to permit field
edit** and a **writable custom field on Contact/Account** — validate it exists and is writable up
front and return **422, never 500** (mirror HubSpot's field-validation / soft-pause on missing
scope). Preserve crm-writeback **G2**: the CRM read-side characterization tests must stay
byte-identical.

## In-repo blueprint (shipped, tested; on master)

- **HubSpot writeback (the pattern to mirror):**
  `docs/planning/crm-writeback/` (PRD + 4 aspect specs), commits `688f788` (config/validation/API),
  `10f4640` (push-on-change + backfill), `b45f489` (HubSpot PATCH contact property), `5e2943d`
  (frontend writeback card).
- **Salesforce connection + client (to consume):** `salesforce-crm-enrichment` — the Salesforce
  client (token refresh, SOQL, sObject access), the Salesforce integration routes, and the
  `salesforce_integrations` model.
- **Provider-generalized read layer:** `crm_enrichment` with a `provider` discriminator;
  `test_crm_provider_generalization.py` characterization tests.
- **Frontend:** shipped HubSpot writeback card + `services/frontend-web/lib/api/` HubSpot/Salesforce
  clients + the Salesforce integration settings page.

## Open questions for the interview (seed)

- **Write target: Contact vs Account?** Read side matches by `Contact.Email`; health is per-customer
  (email) → Contact field is the natural target. Confirm (Account-level would need aggregation).
- **Config home**: generalize onto a shared/provider-tagged writeback config, or add a parallel
  `writeback_*` set of columns to `salesforce_integrations` mirroring HubSpot? (Prefer a
  provider-generalized shape so slice-3 CRMs are cheap.)
- **OAuth scope**: does the shipped Salesforce Connected App flow already request a write-capable
  scope (`api` full), or is a re-consent needed for field edit?
- **Field type**: numeric custom field (0–100) vs text? Validate via the sObject describe API.
- **Trigger reuse**: does the shipped on-change health trigger dispatch provider-agnostically, or is
  it wired to the HubSpot push task specifically?
- **Backfill**: reuse the HubSpot backfill command shape for Salesforce, or a shared provider-param
  backfill?
