# Card — feat/segment-actions (freeform)

**Type:** feat · **Slug:** `segment-actions` · **Branch:** `feat/segment-actions`
**Source:** freeform task from `/rereflect-next` recommendation (no GitHub issue), 2026-07-08.

---

## Brief (from rereflect-next pick)

**Actionable Segments — segment-targeted playbooks + bulk actions on the Customers page.**

Make the just-merged Customer Segments (commit `010bfdf`, M3.4) *actionable* by wiring them into
existing action surfaces, instead of leaving them as a passive label/filter.

### Why this was picked (grounding — not invented)
- Segments merged as the latest commit; the segments PRD explicitly parks the payoff for later:
  *"Automation/playbook/copilot targeting on segments (later fast-follows; hooks noted, not built)"*
  and lists **Playbook segment-targeting** + **Copilot `segment` scope** as the cleanest fast-follows
  (`docs/planning/customer-segments/prd.md:93-96,143`).
- Segments today are a passive label/filter (`AI-TRACKING.md:222`).
- Hardens the core moat loop: churn → health → **playbook** → copilot → automation
  (`AI-TRACKING.md:5`) — operating on cohorts is the reason segments exist.
- Completes M3.4's only unchecked item: *"Bulk actions: export customer list, bulk assign CS owner,
  trigger outreach"* (`AI-TRACKING.md:223`).

### Scope of slice 1 (proposed)
On `/customers`, select a segment/cohort (reuse the `?segment=` filter + the existing
`BulkMarkChurnedDialog` selection pattern) and act on it in bulk:
- CSV export of the filtered customer list
- bulk tag / CS-owner assign
- run an existing playbook on the segment via the `RunPlaybookDropdown` path

### Known caveat (dig into first)
Playbooks' `probability_min` / `probability_max` are `NOT NULL`, so binding a playbook to a *segment
predicate* (instead of a probability band) needs a small migration to relax those
(`docs/planning/customer-segments/prd.md:96`). Also inherits the repo-wide Alembic multi-heads
condition — resolve `merge heads` before adding a migration.

### Explicitly deferred (not slice 1)
- **"Trigger outreach campaign"** — outbound email under self-hosting depends on the operator's own
  SMTP/Resend config; do not gate slice 1 on it.
- Copilot `segment` scope + `@segment:` mention — separate fast-follow (alternate pick).

### Fit guardrails
Open-source / self-hosted / BYOK; no plan-gating or hosted-SaaS assumptions (CLAUDE.md billing/tier
sections are stale). Reuses existing bulk-churn (`/customers/churn-events/bulk`,
`BulkMarkChurnedDialog`) and playbook (`RunPlaybookDropdown`) infrastructure — extends a proven
pattern, not greenfield.

## Reference points to confirm in Phase 2 dig
- Customers page + selection UI: `app/(dashboard)/customers/page.tsx`, `BulkMarkChurnedDialog`,
  `RunPlaybookDropdown` (`components/customers/`).
- Customers list API + `?segment=` filter + serializer (`src/api/routes/customers.py`).
- Bulk churn endpoint precedent: `POST /customers/churn-events/bulk` (`churn_events.py`,
  `churn_event.py` schema).
- Playbook model + CRUD + execution: `playbooks.py`, `playbook_seeder.py`, playbook model
  (`probability_min/max` NOT NULL).
- Segment engine/classifier + `segment` column on `customer_health_scores` (segments commits
  `ba2a4bd`..`d3fbf5e`).
