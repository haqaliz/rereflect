# PRD — Segment Actions (Actionable Customer Segments)

**Slug:** `segment-actions` · **Branch:** `feat/segment-actions` · **Type:** feat (freeform)
**Author:** rereflect-begin-fast pipeline · **Date:** 2026-07-08
**Status:** Draft (pending review gate)

---

## Problem Statement

Customer **Segments** shipped in M3.4 (commit `010bfdf`): every customer is classified into one of 7
rule-based cohorts (`at_risk`, `silent_churner`, `dormant`, `power_user`, `happy_advocate`, `new`,
`unsegmented`) and surfaced as a column + filter on `/customers`. But the segment is **read-only** — an
operator can *see* the at-risk cohort and *filter* to it, yet cannot **act** on it. The segments PRD
explicitly deferred this: *"Automation/playbook/copilot targeting on segments (later fast-follows; hooks
noted, not built)"* (`docs/planning/customer-segments/prd.md:143`). M3.4's own last unchecked roadmap item
is *"Bulk actions: export customer list, bulk assign CS owner, trigger outreach"* (`AI-TRACKING.md:223`).

**Who has the problem:** the self-hosting operator / CS manager who has identified a cohort (e.g. all
`silent_churner`s, or everyone at critical risk) and wants to *do something with the whole group at once*
— export it, tag it, assign it to a CS owner, or run a churn-prevention playbook against it.

**Evidence it's real:** the Customers page has risk/health/segment columns but no action surface; the
selection state (`selectedEmails`, `bulkChurnOpen`) and a "Mark N as churned" button already exist in
`customers/page.tsx:409-420` yet are **dead** — no checkbox column ever populates the selection. The churn
→ health → **playbook** loop (`AI-TRACKING.md:5`, the stated killer feature) can target a customer
predicate today but has **no cohort concept**.

## Goals & Success Metrics

- **G1 — Make segments actionable.** From `/customers`, select a cohort (checkbox rows *or* the whole
  active filter) and run any of 4 bulk actions. Moves M3.4 from PARTIAL toward COMPLETE.
- **G2 — Deepen the moat loop, not bolt on CRM.** Running a churn playbook on a cohort is the headline
  action; it extends the existing `run-batch` path so a segment becomes a first-class playbook target.
- **G3 — Zero regressions to shipped segment/playbook/bulk-churn behavior** (characterization-gated).

**Measurable acceptance:** all four bulk actions work end-to-end against both a row-selection and a
whole-filter cohort; new endpoints are org-scoped and tested; existing playbook single-run, run-batch, and
bulk-churn behavior is byte-identical (characterization tests green); frontend `npm run lint` + `npm run
test` green; backend `pytest tests/ -v` green for touched suites.

**Verification model (OSS):** this is a self-hosted product with no runtime/product telemetry, so success is
**capability-verified + regression-free**, not adoption-measured. There is no "N cohorts acted on" metric to
watch post-merge; the acceptance above is the bar.

**Documentation is a deliverable** (matching every recent shipped feature — Zendesk/Asana/public-API-write):
the new endpoints (`/export`, `/bulk/tags`, `/bulk/assign-owner`, extended `run-batch`) and the new
`tags`/`cs_owner` fields must be documented in `docs/API.md` (+ OpenAPI docstrings) and `docs/SELF_HOSTING.md`,
and the M3.4 tracking rows updated (`AI-TRACKING.md:223`, `DEV-TRACKING.md`).

## User Personas & Scenarios

- **CS manager (operator):** filters to `segment=at_risk`, clicks "Run playbook" → picks "Critical Save" →
  the playbook is queued for every at-risk customer.
- **Ops/analyst:** filters to `segment=power_user`, clicks "Export CSV" → downloads the cohort for a QBR.
- **Team lead:** selects 12 rows, "Assign CS owner" → picks a teammate → those customers now show that
  owner. Or "Tag" → adds `expansion-target` to the cohort.

## Requirements

### Must-have
- **M-1 Cohort selection (frontend).** A checkbox column on the customers `DataTable` (mirrors
  `feedbacks/columns.tsx:91-112`), header select-all-on-page, and a **"select all N matching this filter"**
  affordance so a cohort larger than one page can be targeted. A bulk-actions toolbar appears when a cohort
  is active (rows selected OR "whole filter" chosen).
- **M-2 Cohort contract (backend).** One shared request shape used by all four actions: **either**
  `emails: string[]` **or** `filter: {segment?, risk_level?, search?, include_archived?}`. When `filter` is
  given, the backend resolves matching `CustomerHealth` rows server-side (reusing the exact filter logic of
  `list_customers`), so "whole filter" acts on *all* matching rows, not just the current page. Exactly one of
  `emails`/`filter` must be present. All resolution is org-scoped (`organization_id == current_org.id`).
- **M-3 CSV export.** `GET /api/v1/customers/export` (server-side `StreamingResponse`, `text/csv`,
  `Content-Disposition: attachment`) honoring the same filters as the list. Columns: email, name,
  health_score, risk_level, segment, confidence_level, feedback_count, last_feedback_at, last_active_at,
  churn_probability, tags, cs_owner. Must avoid the per-row sentiment-trend N+1 when streaming a full table
  (omit sentiment_trend from export, or batch-compute).
- **M-4 Bulk tag.** New per-customer `tags` (string list) on the customer-health record + migration.
  `POST /api/v1/customers/bulk/tags` with `{cohort, tags: string[], mode: "add"|"remove"}` (add = set union,
  remove = set difference; trimmed, deduped, max 20 tags/customer, ≤50 chars each — mirror feedback tag
  rules). Returns a bulk summary `{updated, skipped, errors}`.
- **M-5 Bulk assign CS owner.** New nullable `cs_owner_user_id` FK (→ `users.id`, `ondelete=SET NULL`) on
  the customer-health record + migration. `POST /api/v1/customers/bulk/assign-owner` with
  `{cohort, user_id | null}` (null clears). `user_id` must be a member of the current org (validated).
  Returns bulk summary.
- **M-6 Run playbook on cohort.** Extend `RunBatchFilters` + `_apply_run_batch_filters` (`playbooks.py`) to
  accept the cohort contract (`emails` and/or `segment`) in addition to the existing probability range, and
  wire `POST /playbooks/{id}/run-batch` to it. A **queue-safety cap** (max customers per batch, configurable
  constant; over-cap → 413/422 with a clear message) prevents flooding Celery. Reuses existing daily-limit +
  per-customer execution + celery dispatch unchanged.
- **M-7 Surfacing.** Show `tags` and `cs_owner` on the customer row (list serializer + a column/badge) and
  on the profile serializer, so the effects of bulk tag/assign are visible.

### Should-have
- Bulk-action confirmation dialogs mirroring `BulkMarkChurnedDialog` (`{open, onOpenChange, cohort,
  onSuccess}`), with a cohort-size preview ("This will affect N customers") and toast + query invalidation.
- Server resolves and returns the affected count before executing, so the UI can confirm large cohorts.

### Nice-to-have (explicitly later)
- Copilot `segment` scope + `@segment:` mention (separate fast-follow).
- "Trigger outreach campaign" bulk action (needs operator SMTP/Resend — deferred, see Out of Scope).
- Saved cohorts / segment history.

## Technical Considerations

**Services changed:** `backend-api` (routes, models, schemas, migration), `frontend-web` (page, components,
API client), `worker-service` (only if the duplicated `segment_service` needs a touch — it should NOT for
this feature). Analysis-engine unchanged.

**Data model (new migration, single head → `down_revision = "6d7e00e682c7"`):** add to
`customer_health_scores`:
- `tags` — `JSON` (list of strings), nullable, default empty list. **JSON column chosen for v1** (mirrors
  `feedback.tags`, simplest); a join table is *not* needed because **filtering the list by tag is out of
  scope** for this slice — tags are display + bulk-set only. Revisit if tag-filtering is added later.
- `cs_owner_user_id` — `Integer` FK `users.id` `ondelete=SET NULL`, nullable; index on
  `(organization_id, cs_owner_user_id)`.
No relaxation of `churn_playbooks.probability_min/max` is needed — playbook→cohort targeting is a **run-time**
filter, not a playbook-definition change (see Risks).

**API contracts (new / changed):**
- `GET  /api/v1/customers/export` — streaming CSV, same query params as list.
- `POST /api/v1/customers/bulk/tags` — `{cohort, tags, mode}` → `BulkActionSummary`.
- `POST /api/v1/customers/bulk/assign-owner` — `{cohort, user_id|null}` → `BulkActionSummary`.
- `POST /api/v1/playbooks/{id}/run-batch` — extended `RunBatchFilters` (adds `emails?`, `segment?`).
- Shared `Cohort` schema + `resolve_cohort(db, org, cohort) -> list[CustomerHealth]` service, reusing
  `list_customers` filter logic (extract a shared query-builder to avoid drift).
- **Route ordering:** static `/bulk/*` and `/export` paths registered **before** parametric `/{email}`
  routes (`churn_events.py:157-159` precedent).

**Multi-tenancy:** every cohort resolution, bulk write, export, and playbook run is filtered by
`organization_id`; `user_id` for owner-assign validated as an org member; cross-org emails silently skipped
(mirror bulk-churn) OR reported in `errors` (decide in spec — recommend skip-with-count).

**OSS / plan gating:** the playbooks router is gated `require_feature("churn_playbooks")` and customers list
by `customer_health_scores`. Under the OSS pivot all features are unlocked at the plan-config level — **leave
the existing `require_feature` decorators in place unchanged** (do not add new gates, do not remove existing
ones). New bulk/export endpoints inherit the customers-router auth (JWT + org) and admin/owner checks where
mutating (tag/assign/run are mutations → `require_admin_or_owner`; export is a read).

**Reuse (not greenfield where avoidable):** bulk summary shape from `ChurnEventBulkCreate`/`BulkSummary`;
CSV *building* differs (server-side stream vs the client-side `exportChurnEventsCsv` precedent — but the
column logic can be shared conceptually); frontend selection via the shared `DataTable`'s existing
`rowSelection`/`onRowSelectionChange` props (needs a `getRowId: row => row.customer_email` so selection keys
are emails, not indices — small shared-component change) and a checkbox column per the feedbacks precedent.

## Risks & Open Questions

- **R-1 (resolved) — playbook NOT-NULL migration NOT needed.** `probability_min/max` stay `NOT NULL`;
  cohort targeting rides `run-batch` run-time filters. The card's caveat is superseded by the dig.
- **R-2 — Alembic single head.** Confirmed head `6d7e00e682c7`; the card's "6 heads" note is stale. New
  migration branches from it; no merge.
- **R-3 — Queue flooding.** "Run playbook on whole filter" could queue thousands of executions. Mitigate
  with a hard per-batch cap + affected-count confirmation in the UI. Cap value TBD in spec (propose 500,
  matching the CRM writeback backfill cap precedent).
- **R-4 — Export N+1.** `list_customers` computes sentiment trend per row; a full-table stream must not do
  that per row. Mitigation: omit sentiment_trend from CSV, or batch-compute. (Recommend omit for v1.)
- **R-5 — `segment_service` duplication.** Backend + worker copies must stay in sync
  (TRACKING.md / commit `19d0c14`). This feature should **not** need to change classification logic — flag
  if any change creeps in.
- **R-6 — Selection semantics.** "Select all N matching filter" must send the *filter*, not N emails, to
  avoid huge payloads. The cohort contract (M-2) handles this.
- **OQ-1 — Cross-org / nonexistent emails in an explicit `emails[]`:** skip-with-count vs error list?
  (Recommend skip-with-count, surfaced in summary.)
- **OQ-2 — Tag bulk mode default:** `add` (union) as default; `remove` explicit. Confirm.
- **OQ-3 — CS-owner off-boarding.** `ON DELETE SET NULL` means removing a user from the org silently
  unassigns every customer they owned. Is silent unassignment acceptable, or does the operator need a
  heads-up (notification / audit-log entry)? Recommend v1: silent SET NULL (no notification), documented as a
  known behavior; revisit if operators ask. **Decision needed at the review gate.**

## Out of Scope

- "Trigger outreach campaign" / outbound email (depends on operator SMTP/Resend config — separate slice).
- Copilot `segment` scope + `@segment:` mention (separate fast-follow).
- ML/clustering segmentation, editable segment rules, multi-segment membership, segment history/time-series
  (all out of scope per the segments PRD and unchanged here).
- Auto-executing actions on segment membership (this feature is operator-triggered bulk actions, not
  automation rules — workflow automation already exists separately).
- Changing how segments/health/usage are computed.
