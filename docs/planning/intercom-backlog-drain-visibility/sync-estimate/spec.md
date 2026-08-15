# Aspect spec — Sync computes + persists the estimate

**Feature:** `intercom-backlog-drain-visibility` (prd.md R2) · **Aspect:** `sync-estimate`

## Problem slice

`_sync_org` must compute `max(0, total_count − conversations_seen)` after the loop and
`_sync_intercom_org_body` must persist it — and the error paths must reset it so a
failed run never leaves a stale number.

## In-scope

- `_sync_org` (intercom_sync.py:193-318): capture the last page's `total_count` (via
  the client 3-tuple; the loop's `search_conversations` call site :203-205 updates);
  after the loop compute `remaining_estimate = max(0, total_count - conversations_seen)`
  (guard: `total_count is None` → estimate `None`); add `backlog_remaining` to the
  result dict (:311-318, additive key).
- `_sync_intercom_org_body` (:366-368): alongside `last_sync_status = "ok"`, persist
  `integ.backlog_remaining = remaining_estimate` (None when total unknown). Commit
  behavior unchanged.
- `_persist_terminal_status` (intercom_sync.py:95-114): set `backlog_remaining = None`
  on both error paths (auth_error :358, transient :403) — stale-number prevention.
- Tests: estimate computed correctly (total > seen, total == seen → 0, total None →
  None), persisted on success, reset on auth error, reset on transient error, result
  dict additive key, `conversations_ingested`/cursor semantics unchanged.

## Out of scope

- Client 3-tuple (client-total-count aspect — consumed here); migration/API;
  frontend.

## Acceptance criteria (testable)

1. `_sync_org` result contains `backlog_remaining` (int or None) per the guard rules.
2. Success run persists it on the row; auth_error and transient_error runs reset it
   to None (pinned).
3. Existing sync behavior characterization (cursor, counters, one-item invariant)
   unchanged; worker suite green.

## Dependencies & sequencing

- After `client-total-count` (consumes the 3-tuple).

## Open questions / risks

- `total_count` semantics vs `conversations_seen` when the boundary `>=` re-fetch
  inflates seen — `max(0, ...)` handles it; a test pins the negative-delta case.
