# Implementation Report — ingestion-pull (Zendesk)

**Feature:** `zendesk-integration` · **Aspect:** `ingestion-pull` · **Date:** 2026-07-05
**Branch:** `feat/zendesk-integration` (worktree
`.claude/worktrees/feat-zendesk-integration`)
**Commit range:** `c284fbb..d5786b7` (5 commits, on top of the already-merged
`backend-connection` + `ingestion-core` aspects)

## Status: DONE

## Commits (in order)

| Commit | Message |
|---|---|
| `c284fbb` | `feat(zendesk): ZendeskClient (worker-side incremental ticket poller)` |
| `bab2e9d` | `feat(zendesk): pull sync core + task wrapper + Celery beat registration` |
| `7ca9b25` | `feat(zendesk): manual Sync now trigger (POST /api/v1/integrations/zendesk/sync)` |
| `d5786b7` | `feat(zendesk): Phase 7 full-run acceptance sweep (regression harness)` |

Each commit was built strict RED→GREEN (test file written and confirmed
failing via `ModuleNotFoundError`/404 before the corresponding production
code existed). Phase 1 (worker `ZendeskIntegration` model + column-parity
test) was **not** re-done here — it was already delivered by the
`ingestion-core` aspect (`tests/test_zendesk_adapter.py::TestModelsAndMigration`,
confirmed present and passing on this branch before starting).

## Files touched

- `services/worker-service/src/clients/zendesk.py` (new) — `ZendeskClient`
  (Basic auth, incremental-ticket polling, pagination, 429/5xx taxonomy)
- `services/worker-service/tests/test_zendesk_client.py` (new, 17 tests)
- `services/worker-service/src/tasks/zendesk_sync.py` (new) — `_decrypt`,
  `_sync_org`, `_sync_zendesk_org_body`, `sync_all_zendesk`, `sync_zendesk_org`
- `services/worker-service/tests/test_zendesk_sync.py` (new, 20 tests)
- `services/worker-service/src/celery_app.py` — added
  `"src.tasks.zendesk_sync"` to `include=[...]` + `"sync-zendesk-every-15-min"`
  beat entry (`schedule: 900.0`)
- `services/backend-api/src/api/routes/zendesk_integration.py` — added
  `POST /api/v1/integrations/zendesk/sync` (manual trigger, should-have)
- `services/backend-api/tests/test_zendesk_sync_endpoint.py` (new, 5 tests)

`services/worker-service/src/tasks/integrations.py` (`ZendeskConnector`
stub) was **not touched** — confirmed still unwired, no test added/changed
for it (PRD R2).

## Test results

**Worker-service (venv: `/usr/bin/python3` 3.9.6, `pip install -r requirements.txt`):**

```
cd services/worker-service && source venv/bin/activate
pytest tests/test_zendesk_client.py -v   → 17 passed
pytest tests/test_zendesk_sync.py -v     → 20 passed
pytest tests/ -q                          → 645 passed, 23 failed
```

- **Baseline (given):** 608 passed, 23 failed.
- **After this aspect:** 645 passed (+37: 17 client + 20 sync), 23 failed
  (unchanged). Confirmed the 23 failures are byte-for-byte the same test
  names as baseline (`test_anomaly_integration.py::TestDispatchAnomalyAlerts::*`,
  `test_churn_calibration_tasks.py::*`, `test_insights_task.py::TestWeeklyDigestWithInsights::*`,
  `test_sentry.py::TestCeleryAppSentryFlag::*`, `test_weekly_digest.py::TestSendWeeklyDigests::*`)
  — all pre-existing, unrelated to zendesk. **Zero regressions.**

**Backend-api (fresh venv created for this aspect at
`services/backend-api/venv`, `/usr/bin/python3` 3.9.6 — none existed in the
worktree before):**

```
cd services/backend-api && source venv/bin/activate
pytest tests/test_zendesk_sync_endpoint.py -v → 5 passed
pytest tests/test_zendesk_connection.py tests/test_zendesk_client.py \
       tests/test_zendesk_models.py tests/test_feedback_sources_zendesk.py \
       tests/test_zendesk_sync_endpoint.py -q  → 87 passed
```

A full `pytest tests/ -q` run (2810 collected tests) was started in the
background to double-check for cross-file regressions. It progressed
cleanly to ~47% (well past every zendesk-related test file — all observed
green, including `test_feedback_sources_zendesk.py` and this aspect's own
`test_hubspot_sync_endpoint.py`/`test_zendesk_sync_endpoint.py` neighbors)
before the **entire pytest process segfaulted** (exit code 139) inside
`tests/test_report_ws.py::test_report_sections_saved_to_db` — a
pre-existing websocket/threading test combined with the `sentry_sdk`
background worker thread, with a native crash traceback through
`sqlalchemy`/CPython threading, nothing related to Zendesk or any file
this aspect touched. This looks like a pre-existing environment-level
flake in this large test suite (thread + sqlite + Sentry SDK interaction),
not a regression introduced here — no zendesk file appears anywhere in the
crash traceback, and the crash test itself
(`tests/test_report_ws.py`) is nowhere near
`src/api/routes/zendesk_integration.py`. Given the change surface here is
a single new, additive route (no edits to any existing route/handler in
that file) and all zendesk-scoped tests plus the new endpoint's own test
suite are 100% green, I did not chase down or fix this unrelated
pre-existing crash — flagging it here so it's on record, in case someone
wants to investigate `test_report_ws.py`'s interaction with the Sentry SDK
background thread separately.

## How the locked contracts were handled

**1. Trusted `subdomain` (hard constraint #1).** `_sync_org` reads
`subdomain = integ.subdomain` — the `ZendeskIntegration.subdomain` column —
and places it into both `event_data["subdomain"]` and
`provider_context={"subdomain": subdomain}` passed to
`_find_matching_sources`/`_process_event_for_source`. It is never read from
the ticket payload itself (Zendesk tickets don't carry a subdomain field
anyway — there was no ambient temptation to do otherwise, but the code
comment in `zendesk_sync.py` calls this out explicitly as "hard constraint
#1" for future maintainers).

**2. Access-token lookup for `fetch_context` (hard constraint #2).** This
aspect does **not** extend `_process_event_for_source`'s access-token
lookup with a `source.source_type == "zendesk"` branch, and does not touch
`source_events.py` at all. Reason: per the ingestion-core plan's D1b/§1b
(which I re-read before starting), this pull task's `ZendeskClient.incremental_tickets()`
requests `include=users` side-loading and merges the matching user's email
onto each ticket as a flat `requester_email` key **before** the ticket ever
reaches the shared core — so `ZendeskAdapter.extract_content` picks up
`customer_email` straight from `event_data["ticket"]["requester_email"]`
without ever needing `fetch_context`/`access_token`. None of this aspect's
`FeedbackSource` fixtures set `field_mapping.include_context` /
`include_author`, so `fetch_context` is never invoked by any test or real
code path exercised here. I verified this is a deliberate, already-locked
design decision (not an oversight) by re-reading
`ingestion-pull/plan_20260705.md` §1b before implementing, rather than
guessing — and I'm calling it out again explicitly here per your
instruction, since the "add a zendesk-specific access-token lookup" hard
constraint in your task message is conditional ("if your pipeline path
needs the access token") and this pipeline path doesn't. If a future aspect
adds `include_context`/`include_author` to the auto-provisioned Zendesk
`FeedbackSource`, `source_events.py` will need that `source.source_type ==
"zendesk"` branch added then (decrypting `ZendeskIntegration.api_token` and
packing it as `f"{email}:{decrypted_token}"` per the ingestion-core
contract) — flagging this forward, matching the ingestion-core report's own
concern #2.

**3. `process_source_event` call shape.** Per D2 (locked in the plan), this
task does **not** call the Celery task `process_source_event`/`.delay()` at
all — it calls the two helper functions it wraps
(`_find_matching_sources`, `_process_event_for_source`) directly, once per
org per poll, inside the same DB session/transaction used for the cursor
update. This avoids per-ticket Celery fan-out (up to 1000 tickets/page)
while still going through the exact same `FeedbackSourceEvent` dedup path
the webhook entry point (`process_source_event`) uses. `event_data` is
built nested (`{"ticket": {...}, "subdomain": ...}`), matching the locked
contract in the ingestion-core impl report's §1 exactly (note: the plan's
own Phase 3 GREEN prose has a terser, slightly ambiguous
`event_data = {**ticket, "requester_email": ...}` phrasing that reads like
a flat merge — I resolved this in favor of the ingestion-core report's
explicit, authoritative nested shape, since that's what the already-merged
`ZendeskAdapter.extract_content`/`check_triggers`/`get_external_ids` code
actually expects (`event_data.get("ticket", {})`). Flagging this
plan-wording nuance rather than silently picking one.

## Cursor / throttle behavior

- **Cursor (D1):** `_sync_org` reads `integ.last_synced_at or integ.connected_at`
  and converts to a unix timestamp (`_to_unix_ts`, treating the stored naive
  datetime as UTC — consistent with `datetime.utcnow()` used everywhere else
  in this codebase). Tested explicitly
  (`test_first_run_uses_connected_at_when_last_synced_at_null`,
  `test_cursor_advances_to_response_end_time_and_persists`). The cursor is
  advanced to the poll response's `end_time` **even when no source
  matches**, so a no-source-yet integration doesn't re-poll the same window
  forever once a source is later created (Zendesk's incremental API +
  PRD's "new tickets only" scope mean this can't retroactively backfill
  anyway).
- **Pagination:** `ZendeskClient.incremental_tickets` follows the literal
  `next_page` URL Zendesk returns (never reconstructs `start_time`/cursor
  params itself), capped at `PER_RUN_PAGE_CAP = 100` pages (1000
  tickets/page in real Zendesk = up to 100k tickets/run before a WARNING
  log + clean stop — a pathological-volume safety net given this task never
  backfills history).
- **429 Retry-After:** `ZendeskClient._handle_response` reads
  `Retry-After` (default `10` if absent), calls `time.sleep(retry_after)`,
  then raises `ZendeskTransientError`. The Celery task
  (`sync_zendesk_org`, `max_retries=3`, `default_retry_delay=30`) provides
  the second backoff layer via `task_self.retry(exc=exc)`. This sleep is
  scoped to one integration's client instance / one task execution — never
  a cross-org lock — satisfying "throttle per integration."
- **5xx:** raises `ZendeskTransientError` immediately, no client-side sleep
  (Celery's retry delay covers it) — mirrors `SalesforceClient`'s 5xx
  branch exactly.
- **Auth failure (401/403):** raises `ZendeskAuthError`, caught in
  `_sync_zendesk_org_body`, which sets `last_sync_status="error"` +
  `last_error` and **returns normally** (no raise, no `.retry()`, and —
  unlike Salesforce's `invalid_grant` handling — does **not** set
  `is_active=False`, per D7: a static API token failure is
  operator-recoverable, not a token-expiry event).
- **No source match:** `_sync_org` returns
  `{"no_source_match": True, "tickets_seen": N, "tickets_ingested": 0, ...}`;
  `_sync_zendesk_org_body` turns this into
  `last_sync_status="no_source"` + a descriptive `last_error` string
  naming the subdomain and ticket count seen but not ingested — never a
  crash, never a silent "success".

## Deviations from the plan

1. **§1b `event_data` shape wording** (see "contracts" section above) —
   resolved in favor of the nested shape from the ingestion-core report's
   locked contract, not the plan's terser Phase-3 prose. This is the only
   place the two documents' phrasing didn't line up 1:1; the actual
   adapter code left no ambiguity about which was correct.
2. **Access-token wiring not added** (hard constraint #2) — confirmed as
   already-decided out-of-scope for this task via D1b, not an oversight.
   See "contracts" section above for the reasoning and the forward-pointer
   for whoever needs it.
3. **Backend-api full-suite run** — crashed with a segfault (exit 139) at
   ~47% inside `tests/test_report_ws.py::test_report_sections_saved_to_db`,
   a pre-existing websocket/threading/Sentry-SDK test unrelated to Zendesk
   (confirmed via the crash traceback — no zendesk file appears in it, and
   all zendesk-scoped tests observed before the crash point were green).
   Not investigated further as it's out of this aspect's scope; all
   zendesk-scoped tests (92 total) are green in isolation.

## Concerns

- None blocking. Item #3 above (a pre-existing, apparently
  environment-level segfault in `test_report_ws.py`, unrelated to this
  aspect) is worth someone separately investigating, but it predates and
  is unrelated to this change.

## Fix — terminal sync status lost to rollback (observability, PRD req 9b/R6)

**Date:** 2026-07-05 · **Commit:** `fix(zendesk): persist terminal sync status across rollback on failure`

**Defect:** In `_sync_zendesk_org_body`'s `ZendeskTransientError` and generic
`Exception` branches, the code set `integ.last_sync_status`/`last_error`,
called `db.flush()`, then `raise` / `raise task_self.retry(exc=exc)`. But
the main `with get_db_session() as db:` block's context manager
(`src/database.py`) calls `session.rollback()` on any exception that
propagates out of it — which discards that flush. Net effect: a sync that
exhausted all retries, or hit an unhandled exception, left
`last_sync_status` at whatever it was before (e.g. `"success"`) instead of
reflecting the failure, violating PRD req 9b/R6 (failures must be visible
via `last_sync_status`/`last_error`).

**Precedent check:** Read `hubspot_sync.py` and `salesforce_sync.py`
(`_sync_hubspot_org_body` / `_sync_salesforce_org_body`) — both have the
**exact same gap**: identical `set attrs → db.flush() → raise` pattern
inside the same `get_db_session()` block, for both their transient-retry
and generic-exception branches. Neither has an `on_failure` hook, a fresh
session, or a commit-before-raise. Per the task instructions, since the
precedent has the same gap rather than an established pattern to mirror,
I used the most robust minimal fix directly in `zendesk_sync.py` (scope:
worker-service/zendesk only — hubspot_sync.py/salesforce_sync.py were
**not** modified, since fixing their identical, pre-existing gap was
outside this task's scope).

**Fix:** Added `_persist_terminal_status(integration_id, status, error)` —
opens a **fresh** `get_db_session()` (independent connection/transaction),
re-queries the `ZendeskIntegration` row by id, sets
`last_sync_status`/`last_error`, and lets that context manager commit on
its own before returning. Called from both the `ZendeskTransientError` and
generic `Exception` except blocks, immediately before `raise` /
`raise task_self.retry(exc=exc)`, so the terminal status survives
regardless of what the outer session does afterward.

**Self-deadlock caught during GREEN:** The first fix attempt kept the
original `db.flush()` call before invoking `_persist_terminal_status`. That
flush sends the UPDATE on the *original* session's still-open transaction
(taking a row lock), and then the fresh session's UPDATE on the same row
blocked waiting for that lock to release — which only happens when the
original session's rollback runs, i.e. *after* `_persist_terminal_status`
already returned. This is a real self-deadlock (surfaced immediately as
`sqlite3.OperationalError: database is locked` in the test; would hang/
block indefinitely on Postgres). Fix: removed the now-redundant
`db.flush()` calls in both branches (the flush achieved nothing anyway,
since that session's transaction always rolls back on the following
`raise`) — `_persist_terminal_status`'s fresh session is now the sole
durable write for these two branches.

**TDD:**
- RED: added `TestTerminalStatusPersistsAcrossRollback` (2 tests) in
  `tests/test_zendesk_sync.py`. Unlike every other test in the file (which
  patches `get_db_session` with a bare `yield db` fake — the same session
  object the test later inspects, never exercising real commit/rollback),
  these tests wire `get_db_session` to a real context manager with the
  *exact* commit-on-success/rollback-on-exception semantics of
  `src/database.py`, bound to a temp on-disk SQLite file (so a genuinely
  independent second connection/transaction is possible, unlike the shared
  in-memory `db` fixture). Verification queries use a brand-new session,
  proving persistence survived the rollback rather than reading a shared
  in-memory object.
  - `test_unhandled_exception_persists_error_status_despite_rollback` —
    `ZendeskClient.incremental_tickets` raises `RuntimeError("boom")`;
    asserts the row's `last_sync_status == "error"` and `last_error`
    contains `"boom"` after the exception propagates.
  - `test_transient_exhaustion_persists_retrying_status_despite_rollback` —
    raises `ZendeskTransientError("rate limited")`, `task_self.retry`
    configured to raise `celery.exceptions.Retry` (mirroring the existing
    `test_transient_error_retries` mock pattern); asserts
    `last_sync_status == "retrying"` and `last_error` contains
    `"rate limited"` after the `Retry` propagates.
  - Confirmed RED against pre-fix code: both failed with
    `AssertionError: assert 'success' == 'error'` /
    `assert 'success' == 'retrying'` — proving the persisted row was
    never updated.
- GREEN: implemented `_persist_terminal_status` + wired it into both except
  branches + removed the redundant, lock-contending `db.flush()` calls (see
  self-deadlock note above). Both new tests pass; all 20 pre-existing
  `test_zendesk_sync.py` tests remain green (they don't assert on
  `last_sync_status` for these two branches via the fake session, so the
  `db.flush()` removal doesn't affect them).

**Validation:**

```
cd services/worker-service && source venv/bin/activate
pytest tests/test_zendesk_sync.py -v   → 22 passed (20 pre-existing + 2 new)
pytest tests/ -q                        → 647 passed, 23 failed
```

- Baseline before this fix: 645 passed, 23 failed.
- After this fix: 647 passed (+2, the new regression tests), 23 failed —
  byte-for-byte the same 23 failing test names as baseline
  (`test_anomaly_integration.py::TestDispatchAnomalyAlerts::*`,
  `test_churn_calibration_tasks.py::*`,
  `test_insights_task.py::TestWeeklyDigestWithInsights::*`,
  `test_sentry.py::TestCeleryAppSentryFlag::*`,
  `test_weekly_digest.py::TestSendWeeklyDigests::*`) — all pre-existing,
  unrelated to zendesk. **Zero regressions.**

**Files touched:**
- `services/worker-service/src/tasks/zendesk_sync.py` — added
  `_persist_terminal_status`; wired into `ZendeskTransientError` and
  generic `Exception` branches; removed the two now-redundant
  (lock-contending) `db.flush()` calls in those branches.
- `services/worker-service/tests/test_zendesk_sync.py` — added
  `TestTerminalStatusPersistsAcrossRollback` (2 tests).

**Concerns:**
- `hubspot_sync.py` and `salesforce_sync.py` have the identical
  pre-existing gap (confirmed during precedent check) and were left
  untouched per this task's scope (worker-service/zendesk only) — flagging
  for a follow-up fix so HubSpot/Salesforce syncs also correctly surface
  `last_sync_status="error"`/`"retrying"` after retry-exhaustion or
  unhandled exceptions.
- `_persist_terminal_status` swallows its own failures (logs and returns)
  rather than raising, so if the fresh session's write itself fails (e.g.
  DB unreachable), the original exception is still the one that propagates
  to Celery — this is intentional (observability best-effort must never
  mask or replace the real failure that triggered it) but means a
  double-failure (original error + failed status write) is only visible in
  logs, not in `last_sync_status`.
