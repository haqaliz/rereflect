# Aspect Spec — usage-history-snapshot

Parent PRD: `../prd.md`
Sibling (predecessor): `../rollup-rewindow-fix/spec.md`

## Problem slice & outcome

`customer_usage` is one **mutable** row per `(organization_id, customer_email)` — it records the
customer's usage *now* and keeps nothing about the customer's usage *then*. There is therefore no
value anywhere in the system to compare today's engagement against, which is exactly the blocker
already recorded in the repo's own roadmap.

Outcome: a durable, bounded, daily-per-customer snapshot table (`customer_usage_history`) written
by the existing 04:00 UTC scan, so that a later aspect can answer "what was this customer's
`active_days_14d` about 14 days ago?" with a single indexed lookup — and so that the table cannot
become the next unbounded-growth defect, because its prune task ships in the same change.

This aspect delivers **storage only**. It computes no trend, changes no score, and exposes no API.

## Evidence (observed, verified in this worktree)

- `CustomerUsage` is a single mutable row keyed by a unique `(organization_id, customer_email)`
  constraint — `uq_customer_usage_org_email`
  (`services/backend-api/src/models/customer_usage.py:81-92`). No history column, no history table.
- `recompute_usage_scores` already opens one session, loads **every** rollup row
  (`rows = db.query(CustomerUsage).all()`) and iterates it
  (`services/worker-service/src/tasks/usage_metrics.py:330-350`), committing once at the end
  (`:349-350`). The snapshot write has a free ride on a scan that already exists.
- Beat entry `recompute-usage-scores-daily` runs `crontab(hour=4, minute=0)`
  (`services/worker-service/src/celery_app.py:216-220`).
- The snapshot shape has a direct precedent: `CustomerHealthHistory` — integer PK, `organization_id`
  FK, flat scalar snapshot columns, a timestamp, and two composite indexes declared in
  `__table_args__` (`services/backend-api/src/models/customer_health_history.py:6-33`).
- The prune precedent is well established in beat: `purge-old-webhook-deliveries` (Sun 02:15),
  `purge-old-automation-executions` (Sun 02:30), `purge-playbook-executions` (Sun 03:00),
  `purge-old-calibration-models` (Sun 03:30) — `celery_app.py:179-215`. The task body precedent is
  `purge_old_executions` (`worker-service/src/tasks/churn_playbooks.py:65-87`): a module-level
  retention constant, `datetime.utcnow() - timedelta(days=N)` cutoff, a single
  `.delete(synchronize_session=False)`, `db.commit()`, and a `{"status": ..., "deleted": N}` return.
  The retention constant itself lives next to the logic — `EXECUTION_RETENTION_DAYS = 90`
  (`worker-service/src/services/playbook_engine.py:30`, and again in
  `worker-service/src/tasks/automation.py:17`).
- **D2 is the counter-example this aspect must not repeat:** `usage_event` has no prune task
  anywhere in beat despite a documented 90-day retention
  (`docs/planning/product-usage-enrichment/prd.md:91`).
- **The worker keeps its own no-FK model mirrors.** `CustomerUsage` is redefined inside
  `services/worker-service/src/models/__init__.py:969-996` as a "lightweight mirror of backend-api
  model" with `organization_id = Column(Integer, nullable=False, index=True)` and **no
  ForeignKey**. `CustomerHealthHistory` is likewise mirrored at `:480`. Column parity between the
  two definitions is enforced by explicit tests — e.g.
  `test_worker_and_backend_crm_enrichment_columns_match`
  (`worker-service/tests/test_hubspot_sync.py:137`) and its siblings at `:180`, `:225`, `:272`, and
  `worker-service/tests/test_salesforce_sync.py:809`.
- **Live** `alembic heads` in `services/backend-api` returns exactly one revision:
  `u4v5w6x7y8z9 (head)`, across 81 files in `alembic/versions/`. Single head confirmed by running
  it, not by parsing it.
- Worker tests run against `sqlite:///:memory:` (`worker-service/tests/conftest.py:42-44`), and
  there is **no** `on_conflict_do_update` / `postgresql.insert` usage anywhere in `services/` — so
  a Postgres-dialect upsert has no precedent and would not be exercisable by the test suite.

## In scope

- **Model.** New `CustomerUsageHistory` in `services/backend-api/src/models/customer_usage_history.py`,
  exported from `src/models/__init__.py` alongside the existing `CustomerHealthHistory` /
  `CustomerUsage` exports (`backend-api/src/models/__init__.py:25`, `:54`, `:92`, `:127`).
  - `id` — Integer PK.
  - `organization_id` — Integer, FK `organizations.id`, `ondelete="CASCADE"`, not null.
  - `customer_email` — String(255), not null.
  - `snapshot_date` — `Date`, not null, **UTC** (the calendar date of `datetime.utcnow()` at run
    time, consistent with the `datetime.utcnow()` used throughout the usage pipeline —
    `usage_metrics.py:332`).
  - Snapshot payload, all nullable, mirroring the rollup at snapshot time: `active_days_7d`,
    `active_days_14d`, `active_days_30d`, `login_count_30d`, `distinct_feature_count`,
    `usage_score`, `last_active_at`.
  - `created_at` — DateTime, default `datetime.utcnow`.
  - `UniqueConstraint(organization_id, customer_email, snapshot_date)`.
  - `Index(organization_id, customer_email, snapshot_date DESC)` for the lookback query.
- **Worker mirror.** The matching no-FK `CustomerUsageHistory` class in
  `services/worker-service/src/models/__init__.py`, following the `CustomerUsage` mirror style
  (`:969-996`) — `organization_id` as a plain indexed Integer, identical column names and types.
- **Column-parity test** for the two definitions, in the style of
  `test_worker_and_backend_crm_enrichment_columns_match`.
- **Alembic migration** creating the table plus both constraints/indexes, on top of the live single
  head. Downgrade drops the table.
- **Daily batch write** inside `recompute_usage_scores` (`usage_metrics.py:307-355`): after the
  existing per-row loop, write one snapshot row per scanned rollup row for today's UTC date, as a
  **single batched insert** (e.g. `db.bulk_save_objects` / `add_all` of pre-built mappings) — not
  one INSERT per customer, and not one query per customer to check existence.
- **Same-day idempotency, dialect-neutral.** Re-running the task on the same UTC date must leave
  exactly one row per `(org, email, snapshot_date)` and must not raise. Implement by resolving
  today's existing snapshot keys in **one** query (or one bounded delete of today's rows) before the
  batch insert — no `ON CONFLICT`, since it has no precedent here and SQLite-backed tests could not
  exercise it.
- **Prune task**, shipping in the same change: `purge_old_usage_history` in
  `worker-service/src/tasks/usage_metrics.py`, `@shared_task` with an explicit `name=`, module-level
  `USAGE_HISTORY_RETENTION_DAYS: int = 180`, cutoff date computed from `datetime.utcnow()`, single
  `.delete(synchronize_session=False)`, `db.commit()`, `{"status": "complete", "deleted": N}` return.
- **Beat registration** of that prune task in `celery_app.py`, in the existing weekly purge block
  (`:179-215`), at a slot that collides with none of 02:15 / 02:30 / 03:00 / 03:15 / 03:30 / 03:45 /
  04:00 / 04:15, with the same one-line comment style as its neighbours.
- Retention configurable via a single named constant (env override optional; if added, the constant
  remains the documented default).

## Out of scope

- **Retroactive backfill of snapshots from `usage_event`** — explicitly excluded by the PRD
  ("Out of Scope"). The table starts empty and warms up. That is the accepted cold-start cost, and
  the `insufficient_history` state that makes it legible belongs to `trend-detection-and-health`.
- Trend computation of any kind: `usage_trend_state`, `usage_trend_pct`, the 12–16 day tolerance
  band, the minimum-baseline floor, the usage-component penalty — all `trend-detection-and-health`.
- Any change to `usage_score`, `health_score`, `churn_risk_component`, `churn_probability`, or
  segment classification. This aspect writes rows and reads none.
- Any API endpoint or response field exposing the snapshot; any frontend surface.
- Re-deriving the rolling windows (`active_days_7d/14d/30d`) — that is `rollup-rewindow-fix`. This
  aspect **snapshots whatever the rollup row holds** after that aspect's re-derivation has run.
- Adding `active_days_14d` to `customer_usage` — also `rollup-rewindow-fix`.
- D2 (`usage_event` retention and O(lifetime) reprocessing) and D3 (swallowed enqueue). This aspect
  reads no `usage_event` rows at all.

## Acceptance criteria (testable)

1. After one `recompute_usage_scores` run over N `customer_usage` rows, `customer_usage_history`
   contains exactly N rows, all with `snapshot_date` equal to the UTC date of the run.
2. Each snapshot row's `active_days_7d`, `active_days_14d`, `active_days_30d`, `login_count_30d`,
   `distinct_feature_count`, `usage_score` and `last_active_at` equal the corresponding
   `customer_usage` values **as of the end of that run** (i.e. after the score recompute, not
   before).
3. Running `recompute_usage_scores` twice on the same UTC date yields exactly one row per
   `(organization_id, customer_email)` for that date, and the second run raises no
   `IntegrityError`.
4. Two runs on two different UTC dates yield two rows per customer, one per date.
5. Rows for two organizations with the **same** `customer_email` coexist and are distinguishable by
   `organization_id`; a query scoped to one org returns only that org's rows.
6. Deleting an `organizations` row cascades away that org's `customer_usage_history` rows (FK
   `ondelete="CASCADE"`, asserted on the backend-api model).
7. **Not N+1:** the snapshot write issues a bounded number of statements independent of row count —
   asserted by counting emitted SQL statements (e.g. a SQLAlchemy `before_cursor_execute` counter)
   across a fixture of ≥50 customers and showing it does not scale linearly with customer count.
8. The lookback query the next aspect will use —
   `WHERE organization_id = ? AND customer_email = ? AND snapshot_date BETWEEN ? AND ?
   ORDER BY snapshot_date DESC` — is served by the declared composite index (asserted structurally:
   the index exists on `(organization_id, customer_email, snapshot_date)` in both the model and the
   migration).
9. `purge_old_usage_history` deletes rows with `snapshot_date` strictly older than
   `USAGE_HISTORY_RETENTION_DAYS` (180) days before now, leaves rows inside the window untouched,
   returns the deleted count, and is idempotent (a second immediate run deletes 0).
10. `purge_old_usage_history` is registered in `celery_app.py`'s `beat_schedule` — asserted by a
    test that reads the schedule dict, so the D2 failure mode (task exists, never scheduled) cannot
    recur silently.
11. The worker mirror and the backend-api model declare an identical column-name set — asserted by a
    parity test in the style of `test_worker_and_backend_crm_enrichment_columns_match`.
12. `alembic upgrade head` then `alembic downgrade -1` applies and reverts cleanly, and
    `alembic heads` still reports exactly **one** head after the new revision is added.
13. Health scores are unaffected: a characterization fixture's health scores are identical before and
    after this aspect, at any usage weight (this aspect writes only to a new table).

## Dependencies & sequencing

- **Second aspect.** Depends on `rollup-rewindow-fix` landing first, for two reasons:
  1. `active_days_14d` does not exist on `customer_usage` until that aspect adds it, and it is a
     snapshot column here (AC 2).
  2. Snapshotting **frozen** window values would durably persist the D1 defect — every archived row
     would be wrong, and no later fix could repair history.
- `trend-detection-and-health` depends on this aspect: it is the sole consumer of the table.
- **Migration ordering.** Author this migration on top of the `rollup-rewindow-fix` revision, not on
  today's head. Run a **live** `alembic heads` from `services/backend-api` (its venv has the binary;
  it is not on the ambient PATH) immediately before authoring — static parsing of
  `alembic/versions/` has repeatedly produced a false "multiple heads" reading. Live output at the
  time of writing: `u4v5w6x7y8z9 (head)`, single.
- No frontend, API, or analysis-engine dependency in either direction.

## Open questions & risks

- **Snapshot write placement vs. the existing commit.** `recompute_usage_scores` commits only
  `if updated:` (`usage_metrics.py:349-350`). The snapshot must be written on **every** run,
  including a run where no score changed — otherwise a fully steady population produces no history
  at all and the trend never warms up. The plan must make the commit unconditional (or add a second
  guarded commit) and state which.
- **Partial-failure semantics.** If the batch insert fails mid-run, does the score-recompute work in
  the same session roll back with it? Decide explicitly: either one transaction (snapshot failure
  costs that day's score update) or two (snapshot failure is logged and swallowed, scores persist).
  The second is safer for the shipped behaviour of the existing task; whichever is chosen must not
  silently swallow the error without a logged `logger.error` — D3 is the cautionary precedent for
  swallowed failures.
- **Retention value.** 180 days is the PRD default and comfortably exceeds the 12–16 day lookback
  band, giving ~12× headroom. Volume at 10k customers × 180 days ≈ 1.8M rows. If an operator ever
  wants a shorter window, the constant is the single edit point; per-org configurability is not in
  scope.
- **Timezone.** `snapshot_date` is the UTC calendar date. An operator in UTC+13 will see a snapshot
  boundary that does not match their local midnight. Accepted: it is consistent with `datetime.utcnow()`
  used pipeline-wide and with the 04:00 UTC beat slot; per-org timezones are not modelled anywhere in
  this pipeline.
- **A missed day is normal, not exceptional.** Worker downtime, a deploy, or an org installed
  mid-week all produce gaps. This aspect makes no attempt to fill them — no catch-up write for
  yesterday. Gap tolerance is the consumer's problem and is already specified as the 12–16 day band
  in the parent PRD (M3).
- **Row count on the first run.** The very first execution inserts one row per existing
  `customer_usage` row in a single batch. On a large install that is one large INSERT; if the plan
  finds that unacceptable, chunk the batch (e.g. 1000 rows per flush) — still not N+1, and AC 7
  remains satisfiable.
- **The prune task is the whole point of not repeating D2.** It must be reviewed as a shipping
  requirement of this aspect, not deferred to a follow-up — AC 10 exists specifically so "written
  but never scheduled" fails the build.
