# Card — feat/crm-churn-labels (freeform, no GitHub issue)

**Type:** feat
**Slug:** crm-churn-labels
**Branch:** feat/crm-churn-labels
**Source:** `rereflect-next` handoff (2026-07-15). No GitHub issue — freeform.

## Brief (from rereflect-next handoff)

Wire the org's connected CRM (HubSpot + Salesforce, both shipped in M3.1/M3.1b) as a
churn-label source, closing the item `PRD-ADVANCED-CHURN-PREDICTION.md` §9 line 469 deferred
to "Future integration milestones (M3.1, M3.2)" — both now COMPLETE per `AI-TRACKING.md`.
Detect churn signals (Closed Lost opportunity / churned lifecycle stage) and write
`CustomerChurnEvent` rows with the already-defined-but-never-written `source="auto_suggested"`
(`services/backend-api/src/models/churn_event.py:42`). Go provider-agnostic via the existing
`provider` discriminator on `crm_enrichment`, and respect the one-CRM-per-org guard.

**Critical:** `auto_suggested` is excluded from the calibration fit by default and on purpose
(PRD line 457 — silence-proxy bias; enforced at `calibration_refit.py:64,191` and
`churn_calibration.py:50,125`). So the harvester alone trains nothing. The load-bearing slice
is an **operator review queue** that promotes a confirmed CRM suggestion to a `manual` label,
which is what actually feeds the calibrator today and the ~500-label gate on M5.3 tomorrow.
Do not silently flip auto labels into the fit. Scope to CRM only: usage-drop labels are
blocked (`customer_usage` has no history — see `customer-360-unified-timeline` R1) and the
Stripe webhook from that deferred list is dead post-OSS-pivot.

## Why this, why now (moat grounding)

- **Deferred-but-now-unblocked.** `PRD-ADVANCED-CHURN-PREDICTION.md` §9 line 469 defers
  "External label sources (Stripe webhook, HubSpot CRM, Segment)" to "Future integration
  milestones (M3.1, M3.2)". Both shipped: `AI-TRACKING.md` marks M3.1 HubSpot COMPLETE,
  M3.1b Salesforce COMPLETE (2026-07-01), M3.2 usage COMPLETE (2026-06-29). The dependency is
  satisfied; nobody went back for the blocked item.
- **Attacks the roadmap's own killer feature.** `AI-TRACKING.md` line 5 names churn prediction
  the Killer Feature. M5.3 (per-org churn ML) is the one M5 track still unbuilt, gated on
  "~500 labels"; M5.0 already ships a readiness card surfacing `CHURN_LABEL_TARGET = 500`.
  Today's only label sources are the manual "Mark as churned" UI and CSV import (M4.1) — hand
  entry that realistically never reaches 500.
- **The rail is built and unused.** `CHURN_EVENT_SOURCES` already lists `auto_suggested`
  (`churn_event.py:42`, `user_id` NULL at :65) and the calibrator already filters it out.
  Nothing writes it.
- **Fits OSS self-hosted / BYOK.** Single-tenant, the operator's own CRM connection, no central
  cross-tenant data.

## Known caveats carried in from the handoff

1. **Harvesting alone does not move the 500 gate.** PRD line 457 deliberately excludes
   `auto_suggested` from the fit (auto labels reinforce silence-proxy bias); the code enforces
   it in three places. A slice that only writes `auto_suggested` rows builds a counter that
   trains nothing. The review/confirm queue is the load-bearing part.
2. **Usage/Segment is not a viable second label source.** `docs/planning/customer-360-unified-timeline/`
   R1: `customer_usage` keeps only current 7d/30d counters, no history, so a usage-drop is not
   derivable — recorded stance: "we will not fabricate a drop event."
3. **Stripe webhook is dead** post-OSS-pivot (no Stripe billing). Scope to CRM only.
4. **One CRM per org** guard exists (M3.1b) — the harvester must be provider-agnostic via the
   `provider` discriminator rather than assuming HubSpot.
5. **Volume is not guaranteed.** An org's real `Closed Lost` count is whatever it is. This makes
   500 reachable; it does not promise it.

## Open questions for the dig / PRD

- What exactly counts as a churn signal per provider (HubSpot lifecycle stage vs deal stage;
  Salesforce Opportunity `Closed Lost` vs a Contact-level field)? Configurable per org?
- `churned_at` provenance: CRM close date vs detection date.
- `reason_code`: `CustomerChurnEvent` carries a structured reason enum — what does a
  CRM-sourced suggestion map to?
- Does confirming a suggestion mutate the row's `source` (auto_suggested → manual) or write a
  new row? Mutating changes what the calibrator sees; auditability matters.
- Re-suggestion / dedup: what if a customer is already labelled, or a Closed Lost reopens?
- Where does the review queue live (existing `/system/churn-events` page vs a new surface)?
- Does the harvester run on the existing CRM sync beat (daily 03:45 UTC) or its own?
