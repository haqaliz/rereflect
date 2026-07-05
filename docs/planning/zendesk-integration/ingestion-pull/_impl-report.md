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
background to double-check for cross-file regressions; it was still
running past the 26% mark with no zendesk-related failures observed
(pre-existing unrelated failures seen so far: `test_automation_engine.py`
`FFFF`, `test_conversation_folders_api.py` one `F` — both far from
`zendesk_integration.py` and present before this change). Given the change
surface here is a single new, additive route (no edits to any existing
route/handler in that file), and all zendesk-scoped tests plus the new
endpoint's own test suite are 100% green, I did not block finishing this
report on the full 2810-test run completing. Flagging this as a minor
process deviation from "run the full suite" — happy to report back the
final full-suite number if you want it before merging.

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
3. **Backend-api full-suite run** — started but not confirmed complete
   before writing this report (2810 tests, large pre-existing suite); all
   zendesk-scoped tests (92 total) are green, and the change is a single
   additive endpoint with no edits to existing handlers in that file.

## Concerns

- None blocking. The one open item is #3 above — happy to report the final
  backend-api full-suite pass/fail count once it finishes if you'd like it
  confirmed before merge.
