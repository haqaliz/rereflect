# Aspect spec — historical-backfill

**Parent PRD:** `../prd.md` (M7) · **Slug:** `historical-backfill` · **Sequencing:** wave 3

## Problem slice & outcome

**This aspect is the reason the feature meets its goal.** The readiness report
(`ai_readiness.py:74-79`) and the calibrator gate (`churn_calibration.py:50`) count
`CustomerChurnEvent` rows — *actual churns*. An org with 1,000 customers at 5% annual churn
produces ~50/year, so **forward-only harvesting reaches 500 in ~10 years**: it replaces typing
with reviewing and leaves the gate unreachable. The volume lives in the CRM's *history*.

**Outcome:** an operator can run an on-demand, bounded, resumable backfill over a chosen window,
landing years of lost renewals in the review queue in one pass. It produces **suggestions, never
labels** — a volume change, not a trust change. Every row still goes through the M5 human confirm.

## In scope

1. **A distinct, cancellable Celery task** — `backfill_churn_suggestions(integration_id, months)`,
   **not** inside `sync_hubspot_org` (03:15) / `sync_salesforce_org` (03:45): a multi-year
   page-through must never stall the daily enrichment beat. Celery-free body with an injectable
   client (house rule); cancellable via an abort check between pages.
2. **Operator-chosen window** — `months`, **default 24**, explicit hard max (e.g. 60); out of
   range → 422. Floor = `now - months`, compared against the CRM **close date**.
3. **Same decision core as `harvester-core` — must NOT fork it.** Imports the M4 adapters + rule
   verbatim: same `Type`/`pipeline` config match, same `known_emails` customer match, same
   null/unknown → no suggestion, same `suggested_churned_at = CRM close date`. Backfill differs
   only in *which pages it reads*.
4. **Paginated + throttled, both providers** — Salesforce `queryMore` (`nextRecordsUrl` until
   `done`); HubSpot `paging.next.after`. Window-bounded org-wide queries; inter-page throttle so a
   backfill cannot exhaust the org's CRM quota. **The shipped error taxonomy, unchanged:** 429 →
   `Retry-After` sleep → `*TransientError` → `self.retry`; 5xx → transient, no sleep; 403 → scope
   error, no retry; SF 401 → refresh once; **never** touches `is_active`. No new exception types.
5. **Resumable + idempotent** via `UNIQUE(organization_id, provider, external_opportunity_id)`
   (M4) with insert-and-skip-on-conflict. A crash mid-window resumes by re-running; existing
   suggestions are skipped, not recreated. A **rejected** suggestion is never resurrected.
6. **Progress + no silent caps (house rule)** — persist `backfill_status`
   (`idle|running|completed|failed|cancelled`), `backfill_progress` (scanned, created,
   skipped-as-duplicate), `backfill_last_run_at`, `backfill_error` on the integration row. Cap
   truncation → dropped count **logged AND surfaced** with the window actually covered.
7. **Trigger endpoint** — `POST /api/v1/integrations/{provider}/churn-labels/backfill`,
   `require_admin_or_owner`, org-scoped, dispatched via `send_task` (backend cannot import worker
   code). **Broker failure → 502, not 500.** Disabled/empty config (default-deny) → 400; already
   `running` → 409. The M3 provider card gains a "Backfill history" control (window picker + Run)
   rendering status/progress/dropped-count/error from §6.

## Out of scope

- Client accessors, rule, table, review queue, readiness, docs — M1/M2/M4/M5/M6/M8.
- **A looser rule for historical rows.** The decision core does not change because a deal is old.
- Auto-running backfill on enable; auto-confirming backfilled suggestions; backfilling
  `crm_enrichment` or any non-churn history.
- The missing 500/day churn-event rate limit (PRD Out of Scope) — our writes are suggestions,
  human-gated, capped per run.

## Acceptance criteria (testable)

- **AC-1 (not in the daily beat).** `sync_hubspot_org` / `sync_salesforce_org` never invoke the
  backfill body — asserted via a fake whose paging accessors are never called during a normal
  sync. No new beat registered in `celery_app.py`.
- **AC-2 (window).** `months` defaults to 24; a close date older than the floor yields **no**
  suggestion; one inside yields exactly one; `months=0` and `months=<max+1>` → 422.
- **AC-3 (no fork).** The same fake record fed through backfill and the forward harvester produces
  byte-identical suggestion dicts. A record with `Type`/`pipeline` null, unknown, or unconfigured
  yields **zero** suggestions in backfill exactly as in forward harvest (PRD R5).
- **AC-4 (paging).** SF `done: false` + `nextRecordsUrl` is followed until `done: true`; HubSpot
  `paging.next.after` until absent. A 3-page fake yields all 3 pages' suggestions.
- **AC-5 (idempotent + resumable).** Running the same window twice creates the suggestion once;
  the second run reports it skipped-as-duplicate and raises **no** `IntegrityError`. A run aborted
  after page 1 then re-run completes the window with no duplicates. A `rejected` suggestion is not
  recreated.
- **AC-6 (taxonomy).** Mid-page 429 with `Retry-After: 7` sleeps 7 → transient → `self.retry`; 500
  raises transient **without** sleeping; 403 records a scope error, no retry; **no path sets
  `is_active = False`**.
- **AC-7 (no silent cap).** Cap N with N+5 eligible records → exactly N written **and** status
  reports `dropped == 5` **and** a log record names the count and covered window.
- **AC-8 (endpoint).** Member → 403; cross-org id → 404; disabled/empty config → 400; already
  `running` → 409; broker raise → **502**; happy path → 202 with the run's status payload.
  Cancelling mid-run stops before the next page and persists `backfill_status='cancelled'` with
  partial progress; already-written suggestions stay.

**Test style.** Strict TDD, tests first. Real SQLite `db` fixture + a hand-written multi-page Fake
client injected through the M4 client seam (precedent: `FakeJiraClient`). No Celery, no httpx.

## Dependencies & sequencing

**Wave 3 — blocked on `harvester-core` (M4)** for the adapters, decision core, and suggestions
table + unique constraint. Transitively blocked on `provider-churn-fetch` (M1) for the accessors
this aspect extends with paging, and on the M3 config columns. Adds **no** new table; the backfill
status columns extend M3's integration columns. Independent of `readiness-honesty` (M6); feeds
`docs-and-tracking` (M8, wave 4). Per PRD R6 the migration adding the status columns **must
resolve the pre-existing 2-head alembic fork explicitly** — do not silently pick a head.

## Risks

- **The biggest CRM-quota consumer this feature has.** Mitigated by throttle + per-run cap +
  operator-chosen window, and by living outside the daily beat (AC-1).
- **Forking the rule under schedule pressure.** The temptation is a "looser rule for history".
  AC-3 makes divergence a test failure; if the rule must change, change it in M4 for both paths.
- **R1 (PRD) — volume may still not reach 500.** Backfill harvests what exists; we promise no org
  reaches the gate. Per R8 the target is under review — this aspect's value is
  threshold-independent.
- **R3 (PRD) — historical rows are the least verifiable.** A 3-year-old lost renewal is hardest to
  confirm from memory. Mitigated by M4's `evidence` payload, and by never auto-confirming.
- **R4 (PRD) — paging edits touch shipped client code.** Sibling accessors only; M1's enrichment
  lock must stay green. Worker restarts are survivable via AC-5 resumability.
