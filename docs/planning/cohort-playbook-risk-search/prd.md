# PRD — run a playbook on any customer-list cohort

## Problem
The Customers page supports whole-filter cohorts: `segment`, `risk_level`, `search`,
`include_archived`. Export/tag/assign accept all of them. `POST /playbooks/{id}/run-batch`
only accepts `emails` or `segment`, and the frontend helper `cohortToRunBatchFilters` returns
`null` for a risk/search-only cohort, so the dialog blocks the run. This is the only remaining
code gap recorded under AI-TRACKING M3.4.

## Requirements
- R1: backend `RunBatchFilters` accepts `risk_level`, `search`, `include_archived`, validated like
  `GET /api/v1/customers/` (`risk_level` ∈ healthy/moderate/at_risk/critical → 422 otherwise).
- R2: any of those fields selects cohort mode instead of probability-only mode; when combined with
  an explicit probability band, both must match (AND), as segment already does.
- R3: archived customers are excluded by default in cohort mode and included when
  `include_archived: true`.
- R4: `emails` keeps precedence and behaviour (explicit list, unknown skipped, no archived filter).
- R5: `count_only` preview and the 500-cap contract are unchanged.
- R6: frontend `cohortToRunBatchFilters` maps the full filter set; only an empty filter still
  returns `null` (the dialog keeps its "unsupported" guard for that case).

## Out of scope
- Changing the shared `Cohort`/`CohortFilter` contract.
- Bulk tag/assign/export (already support the full set).

## Acceptance
- Backend: risk-only, search-only, include_archived, invalid risk level, count_only-with-risk.
- Frontend: mapping tests for every filter field plus the empty-filter null case.
- Existing run-batch suites stay green.

## Risks
- Cohort mode now triggers on three more fields. A client that previously sent `search: ""` would
  switch from probability-only to cohort mode; the route normalises empty strings to `None`.
