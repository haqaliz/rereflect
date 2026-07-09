# Aspect Spec — bulk-actions-api

**Parent PRD:** `../prd.md` · **Owner agent:** `be-fastapi-specialist`
**Sequence:** after `customer-fields-model`. Provides the shared cohort contract that `playbook-cohort-run`
and `customers-bulk-ui` consume. Blocks `customers-bulk-ui`.

## Problem slice & outcome

Provide the shared **cohort contract** and the three non-playbook bulk actions: server-side CSV export, bulk
tag, and bulk assign-owner. All operator-triggered, org-scoped.

## In scope

- **Shared cohort schema + resolver.** New `src/schemas/cohort.py` `Cohort`:
  `{ emails: list[str] | None, filter: CohortFilter | None }` where
  `CohortFilter = {segment?, risk_level?, search?, include_archived?}`. Pydantic validator: **exactly one** of
  `emails`/`filter` is set (else 422). New `src/services/cohort_service.py`
  `resolve_cohort(db, org, cohort) -> Query[CustomerHealth]` (or list) that:
  - for `emails`: normalizes `.strip().lower()`, filters `CustomerHealth.organization_id == org.id` AND
    `customer_email.in_(emails)`; **skip-with-count** for unknown/cross-org emails (report in summary).
  - for `filter`: **reuses the exact list-filter logic** of `list_customers`. Extract that filter-building
    into a shared helper (e.g. `_apply_customer_filters(query, org, segment, risk_level, search,
    include_archived)`) called by both `list_customers` and `resolve_cohort` (avoid drift — characterize
    `list_customers` output before extracting).
- **CSV export.** `GET /api/v1/customers/export` (read; inherits customers-router auth + org; keep the
  existing `require_feature("customer_health_scores")` gate unchanged). Same query params as the list
  (`segment`, `risk_level`, `search`, `include_archived`, `sort_by`, `sort_order`). `StreamingResponse`,
  `media_type="text/csv"`, `Content-Disposition: attachment; filename="customers-<segment-or-all>.csv"`.
  Columns: email, name, health_score, risk_level, segment, confidence_level, feedback_count,
  last_feedback_at, last_active_at, churn_probability, tags (joined), cs_owner_email. **Omit sentiment_trend**
  (avoids the per-row N+1 at `customers.py:340`). Stream in chunks/pages; do not load the whole org in memory.
- **Bulk tag.** `POST /api/v1/customers/bulk/tags` (`require_admin_or_owner`).
  Body `{cohort: Cohort, tags: list[str], mode: "add"|"remove"}`. Validate tags: trim, dedupe, drop empties,
  ≤50 chars each, cap 20 tags/customer after apply (mirror feedback tag rules). `add` = set union,
  `remove` = set difference, per customer. Returns `BulkActionSummary {matched, updated, skipped, errors}`.
- **Bulk assign owner.** `POST /api/v1/customers/bulk/assign-owner` (`require_admin_or_owner`).
  Body `{cohort: Cohort, user_id: int | null}`. `user_id` must be an **active member of current_org**
  (validate against org membership; else 422); `null` clears. Sets `cs_owner_user_id`. Returns
  `BulkActionSummary`.
- **Shared summary schema** `BulkActionSummary {matched, updated, skipped, errors: list[str]}` (extends the
  `BulkSummary` idea from `churn_events.py`).
- **Route ordering:** register `/export` and `/bulk/*` **before** parametric `/{email}` routes
  (precedent `churn_events.py:157-159`). Prefer a dedicated `customers_bulk` router included before the
  parametric routes, or place the static paths above them in `customers.py`.
- **Docs:** add all three endpoints to `docs/API.md` + OpenAPI docstrings.

## Out of scope

- Playbook run-batch (aspect `playbook-cohort-run`, though it imports `Cohort`/`resolve_cohort` from here).
- Any migration (done in `customer-fields-model`).
- Frontend.

## Acceptance criteria (testable)

- `Cohort` rejects both-set and neither-set (422).
- `resolve_cohort` by `filter` returns the **same** customers `list_customers` would for identical params
  (parity test); by `emails` skips unknown/cross-org and counts them.
- Refactor parity: `list_customers` output unchanged after extracting `_apply_customer_filters`
  (characterization test).
- `/export` streams valid CSV with the specified columns, honors filters, sets attachment headers, and issues
  no per-row sentiment-trend query.
- `/bulk/tags` add/remove produce correct per-customer tag sets, enforce caps, are org-scoped, and return an
  accurate summary; cross-org emails skipped.
- `/bulk/assign-owner` sets/clears owner, rejects non-member `user_id` (422), org-scoped, accurate summary.
- Mutating endpoints require admin/owner (403 for member); export allowed for all authed roles.

## Dependencies & sequencing

Needs `customer-fields-model` (columns). TDD RED-first per endpoint. The `_apply_customer_filters` extraction
must be characterization-gated on `list_customers` first.

## Risks

- Streaming + SQLAlchemy session lifecycle: ensure the generator holds a valid session (yield within request
  scope) and paginates rather than materializing all rows.
- Filter-logic extraction is the highest-drift risk — gate with a parity test before refactor.
