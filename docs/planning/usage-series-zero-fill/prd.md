# PRD — zero-fill the customer usage time series

## Problem
`GET /api/v1/customers/{email}/usage` (`services/backend-api/src/api/routes/customers.py:1656`)
returns `time_series` buckets only for calendar days that have at least one event. A customer
with events on two days in a 30-day window returns two points. Charts render discontinuous
series or misalign the x-axis. Recorded as `TRACKING.md` item (h).

## Requirements
- R1: `days=30|60|90` returns exactly that many daily buckets, oldest → newest, ending today (UTC).
- R2: Days with no events are present with `event_count: 0`.
- R3: Event counts are unchanged for active days; no event outside the window is counted.
- R4: No response-shape change beyond the added zero buckets (`date`, `event_count` unchanged).

## Out of scope
- Frontend chart changes (they consume the same shape).
- Raw-event retention or rollup computation.

## Acceptance
- New tests assert exactly 30 contiguous buckets, zero-filled days, and unchanged totals.
- Existing `tests/test_customers_usage.py` suite green.

## Risks
- The window is redefined from `now - days` to midnight of the oldest bucket, widening it by
  less than 24h. Counts can only gain events that occurred earlier on the oldest day, which were
  already inside the previous rolling window's ambiguity; tests pin the new boundary.
