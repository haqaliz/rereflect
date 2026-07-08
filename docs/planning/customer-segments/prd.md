# PRD — Customer Segments (rule-based)

**Slug:** `customer-segments` · **Branch:** `feat/customer-segments` · **Status:** Draft (pre-gate)
**Source:** freeform — `rereflect-next` handoff, 2026-07-08. Completes M3.4 (`AI-TRACKING.md:220-222`).
**Services touched:** backend-api, worker-service, frontend-web. (analysis-engine untouched.)

---

## Problem Statement

Rereflect surfaces every customer as an individual row on the Customers page with a health score and
churn risk, but gives operators **no way to group customers by behavior**. A CS lead can't answer
"who are my silent churners?" or "which power users should I ask for a testimonial?" without eyeballing
scores one by one. M3.4 (Enhanced Customer 360) shipped the unified timeline and Customer 360 API but
left **Customer Segments** explicitly deferred (`AI-TRACKING.md:222`) — it is the last open piece of the
core Customer-Intelligence area, and the only reason it was deferred is that the team wanted ML
segmentation ("heuristic-only today; no ML segmentation").

Under the open-source, self-hosted, BYOK positioning, a **rule-based/heuristic** segment engine is the
right answer, not a gap — it mirrors how churn already ships as a *calibrated heuristic, stated as such*
(`AI-TRACKING.md:240`). All the signals a segment rule needs already exist and are computed without ML.

**Evidence it's real:** deferred milestone item (`AI-TRACKING.md:222`); the Customers page has risk/health
columns but no behavioral grouping (`app/(dashboard)/customers/page.tsx:203-330`); every downstream AI
surface (automation, playbooks, copilot) can target a customer predicate today but has no cohort concept.

## Goals & Success Metrics

- **G1 — Complete M3.4.** Customer Segments ships; M3.4 can move from PARTIAL toward COMPLETE.
- **G2 — Every customer with a health row gets a segment** (or an explicit "unsegmented" when signals
  are insufficient), visible as a column + filterable on the Customers page and shown on the profile.
- **G3 — Segments are honest.** UI states plainly that segments are rule-based heuristics; no ML claim.
- **G4 — Segment is a reusable predicate.** It lands on the shared serializer so the public REST API
  exposes it for free, and the persisted column is ready to be a target for automation/playbooks/copilot
  (built in later slices).

**Measurable acceptance:**
- Given a customer whose signals match a rule, the classifier returns the expected segment (unit-tested
  against a truth table covering every segment + the priority tiebreaks + the unsegmented fallback).
- `GET /api/v1/customers/?segment=silent_churner` returns only customers in that segment, paginated.
- The Customers page shows a Segment column + a Segment filter dropdown; the profile shows a Segment badge.
- Nightly `recompute_segments` re-derives membership so recency-based segments (Dormant, Silent Churner)
  update without new feedback; on-ingest update keeps it fresh between runs.

## User Personas & Scenarios

- **CS manager**: filters Customers to `at_risk` + `silent_churner` for the week's outreach list.
- **Founder/PM**: filters to `power_user` / `happy_advocate` to source testimonials or beta invites.
- **Operator (self-hoster)**: sees segments populate automatically after wiring feedback (and optionally
  usage events) — no configuration required for the built-in set.

## Requirements

### Must-have (slice 1)
1. **Built-in segment set (fixed, rule-based).** Six segments defined in code, evaluated in **priority
   order, first match wins** (single assignment):

   | Priority | Segment | Rule (all from existing signals) | Signals needed |
   |---|---|---|---|
   | 1 | `at_risk` | `risk_level ∈ {at_risk, critical}` (or `churn_probability ≥ 0.5` when present) | health (always) |
   | 2 | `silent_churner` | usage present AND declining engagement (`active_days_30d` low / `usage_score` dropped) AND sentiment `declining` AND no feedback in ≥30d | usage + sentiment |
   | 3 | `dormant` | `last_active_at` (product) > 30d ago OR (no usage data AND `last_feedback_at` > 60d) | usage or feedback recency |
   | 4 | `power_user` | usage present AND `usage_score ≥ 75` AND `active_days_30d ≥ 15` | usage |
   | 5 | `happy_advocate` | `health_score ≥ 75` AND sentiment `improving`/`stable` (not declining) | health + sentiment |
   | 6 | `new` | `first_seen_at` (or `created_at`) within last 14d AND `feedback_count` low | recency |
   | — | `unsegmented` (null) | no rule matched, or insufficient signals | — |

   Exact thresholds reuse the named constants in `usage_score_service.py:29-85` where applicable; the
   truth table is finalized in the `segment-engine` spec. Priority order and thresholds live in one
   config object so they're trivially adjustable later.
2. **Graceful degradation when usage data is absent.** Usage is opt-in (`usage_component` default 0,
   `customer_usage` row may not exist). Usage-dependent rules (`silent_churner`, `power_user`, and the
   product-recency arm of `dormant`) **only fire when a `CustomerUsage` row exists**; otherwise the
   customer falls through to health/sentiment/recency rules or `unsegmented`. Segments must **never**
   mislabel an entire org as `dormant` just because usage isn't wired.
3. **Persisted `segment` column** on `customer_health_scores` (`CustomerHealth`), nullable String,
   set during `update_customer_health` (on feedback ingest) and by a nightly `recompute_segments` task.
   One Alembic migration chained off the single head `a5b6c7d8e9f0` (+ index for filtering).
4. **List API filter + column.** `GET /api/v1/customers/` accepts `segment=<slug>` (validated against the
   segment allowlist), returns `segment` on each `CustomerListItem`.
5. **Serializer field.** `segment` added to `serialize_customer_profile` Core block → surfaces on the
   internal profile route AND the public REST API (single source of truth, no drift).
6. **Frontend surface.** Segment column (a `SegmentBadge`) + Segment filter `<Select>` on the Customers
   page; Segment badge on the profile header; `segment` added to the API-client row/params/profile types.
   Colors from `--chart-*` CSS vars via `color-mix(in oklch)` (never hardcoded).
7. **Honest labeling.** A short "rule-based" tooltip/label near the Segment filter/column and a one-liner
   on the profile badge or a help affordance, mirroring churn's calibrated-heuristic framing.

### Should-have
- Nightly recompute logs a per-segment count (observability; also seeds a future summary breakdown).
- `sort_by=segment` support on the list (cheap once the column is indexed).

### Nice-to-have (explicitly later slices)
- Segment breakdown card on the Customers list summary.
- Copilot `segment` scope + `@segment:` mention (dig: cleanest hook — fast-follow).
- Playbook segment-targeting (dig: needs a migration to relax `probability_min/max` NOT NULL).
- Automation segment **filter/condition** on existing triggers (fast-follow).

## Technical Considerations

- **Storage:** nullable `segment` (String) + index on `customer_health_scores`
  (`models/customer_health.py:7-86`, unique `(organization_id, customer_email)` at :80). Migration off
  single head `a5b6c7d8e9f0` (**verify with `alembic heads` in Phase 5** — the docs' "6 heads" no longer
  holds per the Phase 2 dig).
- **Classifier:** new pure-function service (e.g. `src/services/segment_service.py`) taking a
  `CustomerHealth` row + optional `CustomerUsage` row + sentiment-trend + returning a segment slug via the
  ordered rule list. Pure/no-DB core → fully unit-testable. Sentiment trend via `compute_sentiment_trend`
  (`health_score_service.py:568-604`).
- **Write paths:** set `segment` inside `update_customer_health` (`health_score_service.py:374-517`) so it
  updates on ingest; nightly `recompute_segments` Celery task mirrors `recompute-usage-scores-daily`
  (`celery_app.py:194-198`, 04:00 UTC) at ~04:15 UTC so it reads fresh usage/health.
- **List API:** `list_customers` (`customers.py:247-347`) — add `segment` param + validation (near
  :24-27 / :252-262), filter clause (:276-306), populate item (:322-337), add to `CustomerListItem`
  (:39-50). Serializer: `customer_profile_serializer.py:57-66` + `CustomerProfileResponse`
  (`customers.py:83-116`).
- **Frontend:** `lib/api/customers.ts` (`CustomerListItem` :8-25, `CustomerListParams` :53, `list()`
  :232-245); page `app/(dashboard)/customers/page.tsx` (columns after :329, filter after :467,
  queryParams :126-133); profile `app/(dashboard)/customers/[email]/page.tsx:647-671`; new
  `components/customers/SegmentBadge.tsx` mirroring `ChurnTimelineBadge.tsx`; `SEGMENT_COLOR` map in
  `lib/constants/churn.ts`.
- **Multi-tenancy:** all reads/writes already org-scoped via `CustomerHealth.organization_id`; classifier
  is org-agnostic (operates on a row) so no leakage risk.
- **Performance:** persisted+indexed column → segment filter is a WHERE clause, no N+1. Nightly recompute
  iterates health rows per org (same shape as usage recompute).

## Risks & Open Questions

- **R1 (honesty):** segments must read as heuristic, not ML. Mitigation: explicit UI copy (must-have #7).
- **R2 (thresholds feel arbitrary):** built-in thresholds may not fit every org. Mitigation: centralize in
  one config object; editable rules are a named later slice. Accept for slice 1.
- **R3 (priority ties):** single-assignment hides secondary membership (a power user who is also at-risk
  shows only `at_risk`). Accepted per the Membership decision; multi-segment tags are a later slice.
- **R4 (usage-absent orgs):** must not over-assign `dormant`. Mitigation: usage-gated rules (must-have #2)
  + truth-table tests for the no-usage path.
- **OQ1:** exact numeric thresholds for `silent_churner` "declining" and `dormant` windows — finalized in
  the `segment-engine` spec against `usage_score_service.py` constants.
- **OQ2:** should `unsegmented` render as a neutral chip or no chip? (Lean: subtle "—/Unsegmented" chip.)

## Out of Scope

- ML / clustering segmentation (KMeans, embeddings) — the deliberate design line.
- User-editable segment rule definitions + a settings editor UI.
- Automation/playbook/copilot **targeting** on segments (later fast-follows; hooks noted, not built).
- New ingestion or external data sources; changes to how health/usage/sentiment are computed.
- Multi-segment membership / segment tags; segment history/time-series.
- Auto-executing campaigns or actions from segment membership.
