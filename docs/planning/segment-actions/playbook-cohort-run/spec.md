# Aspect Spec — playbook-cohort-run

**Parent PRD:** `../prd.md` · **Owner agent:** `be-fastapi-specialist`
**Sequence:** after `customer-fields-model` + `bulk-actions-api` (imports `Cohort`/`resolve_cohort`).

## Problem slice & outcome

Let an operator run an existing churn playbook against a **cohort** (selected emails or a segment/filter),
not just a probability band. This is the headline moat action. **No playbook-model migration** —
`probability_min/max` stay `NOT NULL`; targeting is a run-time filter only.

## In scope

- **Extend `RunBatchFilters`** (`src/schemas/churn_playbook.py`, currently
  `{probability_min?, probability_max?, time_to_churn_bucket?}`) to also accept the cohort contract:
  add optional `emails: list[str]` and `segment: str` (validated against `SEGMENT_SLUGS`). Keep existing
  probability fields working (back-compat: a request with none of the new fields behaves exactly as today).
- **Extend `_apply_run_batch_filters`** (`src/api/routes/playbooks.py:128-157`): when `emails`/`segment`/
  `filter` present, select `CustomerHealth` via the shared `resolve_cohort` / `_apply_customer_filters` from
  `bulk-actions-api` (single source of truth for cohort resolution), intersected with org scope. When only
  probability fields present, unchanged behavior. Define precedence if both segment and probability given
  (recommend: AND them — segment ∧ probability band).
- **Queue-safety cap.** Constant `RUN_BATCH_MAX_CUSTOMERS = 500` (matches CRM-writeback backfill cap). If the
  resolved cohort exceeds it, return **422** with a clear message (`"cohort of N exceeds batch cap of 500;
  narrow the filter"`) — do **not** silently truncate. Log the cap decision.
- **Affected-count preview.** Either a dry-run mode on run-batch (`?count_only=true` → `{matched}` without
  queuing) or ensure the resolver count is cheap so the UI can call it before confirming. Provide whichever
  the UI aspect needs (coordinate: expose `{matched}` in the run-batch response too).
- Existing daily-limit check, per-customer `ChurnPlaybookExecution` creation, and celery dispatch
  (`tasks.churn_playbooks.run_playbook`) **unchanged**.
- Leave the router-level `require_feature("churn_playbooks")` gate as-is (unlocked at plan-config under OSS).
- **Docs:** update the run-batch entry in `docs/API.md` + docstring for the new filter fields + cap.

## Out of scope

- Any change to the playbook model / `probability_min/max` nullability.
- The worker task itself (`churn_playbooks.run_playbook`).
- Non-playbook bulk actions (aspect `bulk-actions-api`).

## Acceptance criteria (testable)

- Run-batch with `probability_min/max` only → identical customer selection + queued executions as before
  (characterization test on `_apply_run_batch_filters`).
- Run-batch with `emails` → queues one execution per resolved (org-scoped, existing) customer; unknown emails
  skipped.
- Run-batch with `segment` → queues for all customers in that segment (whole-cohort, not page-limited),
  org-scoped.
- `segment` + probability band → AND semantics (only customers matching both).
- Cohort > 500 → 422, nothing queued.
- Daily-limit + dispatch behavior unchanged (existing tests still green).
- Invalid `segment` slug → 422.

## Dependencies & sequencing

Needs `customer-fields-model` (columns exist) and `bulk-actions-api` (shared `resolve_cohort` /
`_apply_customer_filters`). If built concurrently with `bulk-actions-api`, the shared resolver must land
first. TDD: characterize existing run-batch RED/GREEN before extending.

## Risks

- Double-counting against the daily limit when a large cohort is queued — confirm the limit check accounts
  for the full cohort size up front, not per-customer mid-loop.
- Cohort resolution must reuse the exact filter logic (no divergent segment filtering) — import from the
  shared helper, do not re-implement.
