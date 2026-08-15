# Aspect spec — Client surfaces search total_count

**Feature:** `intercom-backlog-drain-visibility` (prd.md R1) · **Aspect:** `client-total-count`

## Problem slice

The sync needs Intercom's per-query `total_count` to compute the remaining-backlog
estimate, but `search_conversations` (services/worker-service/src/clients/intercom.py)
parses the payload (:148-154) and drops it, returning a strict 2-tuple
`(conversations, next_cursor)`.

## In-scope

- Widen to a 3-tuple `(conversations, next_cursor, total_count)` where `total_count`
  is `payload.get("total_count")` (int; `None` when absent — defensive). `total_count`
  is per-query (same on every page), so any page's value is the window's total.
- **The load-bearing constraint:** every unpack site + the `_fake_client` fixtures
  (`test_intercom_sync.py:257`, :175-191, `intercom_sync.py:203-205`) update in the
  SAME commit; the existing contract tests are the RED gate. TDD: write the failing
  contract test first (3-tuple), then update consumers.
- Pin with MockTransport: `total_count` present, absent (`None`), and the query-body
  contract unchanged (defaults preserved).

## Out of scope

- Estimate computation/persistence (sync-estimate aspect); migration/API (db-status-api);
  UI (frontend-remaining-row).

## Acceptance criteria (testable)

1. Contract test RED→GREEN: search returns the 3-tuple; `total_count` int when present,
   `None` when absent; existing query-body/URL/taxonomy tests pass unchanged.
2. All consumers (intercom_sync.py + test fakes) unpack 3 values; worker suite green.

## Dependencies & sequencing

- First: sync-estimate consumes the 3-tuple.

## Open questions / risks

- None beyond the mechanical ripple — the dig enumerated every site; the plan lists them
  explicitly so no consumer is missed.
