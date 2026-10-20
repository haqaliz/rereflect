# PRD — usage-metrics hardening

## Problem

The worker's usage-metrics path has three unbounded-growth / scale hazards and
one latent type bug:

1. `usage_events` has no retention purge; the raw log grows forever (#40).
2. `recompute_usage_scores` loads every `customer_usage` row in one `.all()`
   (#41).
3. `process_usage_event` re-aggregates a customer's entire event history on
   every event (#42).
4. `_compute_rollup_from_events` compares naive `utcnow()` with `occurred_at`,
   which breaks with tz-aware input (#43).

## Goals

- Bound raw-event growth with an env-configurable retention purge, wired into
  beat and the beat-integrity test.
- Make the daily recompute memory-bounded per page without changing
  per-customer results or the once-per-customer-per-day snapshot semantics.
- Make the rollup path tz-safe without changing results for naive input.
- Do not regress rollup correctness or idempotency for #42. If an incremental
  delta cannot preserve exact parity, leave it untouched and report blocked.

## Non-goals

- New dependencies, schema migrations, per-org retention config.
- Changing score/trend/health formulas.
- Backfilling or rewriting existing data.

## Acceptance (per issue)

- **#40** `purge_old_usage_events` deletes rows older than
  `USAGE_EVENT_RETENTION_DAYS` (default 90, env-configurable); beat entry
  `purge-old-usage-events` resolves and name-matches; tests prove old deleted /
  recent kept and registration consistency.
- **#41** recompute iterates `customer_usage` in id-ordered pages
  (1000 rows), preserving the per-row recompute, trend classification,
  snapshot-once-per-day and post-commit transition drain; test proves several
  pages are processed.
- **#42** either incremental with exact parity + replay idempotency, or
  deferred with a documented blocker.
- **#43** tz-aware `occurred_at` no longer raises and produces the same rollup
  as the naive equivalent; naive results unchanged.

## Risks / open questions

- **#42 parity:** `customer_usage` stores no processed-event watermark, so a
  replay of an already-counted `external_event_id` cannot be distinguished from
  a first sighting without a schema change. Delta-incrementing `events_total`
  would double-count on retry, and windows/active days age out of trailing
  windows over time. Exact parity therefore requires keeping the recompute.
- **#41 memory:** paging the ORM scan removes the unbounded row list, but the
  snapshot payload list is still accumulated for the single post-loop write.
  Bulk-writing snapshots per page would change the commit/failure semantics and
  is left as a follow-up.
- **#40 NULL `occurred_at`:** retention filters on `occurred_at < cutoff`, so
  rows with no timestamp are retained (never silently dropped).
