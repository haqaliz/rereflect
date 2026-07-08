# Aspect Spec — segment-engine

**Parent PRD:** `../prd.md` · **Services:** backend-api, worker-service · **Sequence:** 1st (others depend on it)

## Problem slice & outcome

Every non-archived `CustomerHealth` row resolves to exactly one segment slug (or `unsegmented`),
persisted on the row, kept fresh on feedback ingest and by a nightly recompute. Pure, unit-tested,
rule-based — no ML.

## In scope

1. **Segment definitions (code, one config object).** Ordered list of 6 rules + `unsegmented` fallback,
   evaluated top-down, first match wins. Slugs: `at_risk`, `silent_churner`, `dormant`, `power_user`,
   `happy_advocate`, `new`. Priority + thresholds in one place (e.g. `SEGMENT_RULES` in
   `src/services/segment_service.py`). Reuse `usage_score_service.py:29-85` thresholds where applicable.
2. **Classifier (pure function).** `classify_segment(health_row, usage_row_or_None, sentiment_trend) -> slug`.
   No DB access inside the core → fully unit-testable. A thin `resolve_segment(org_id, email, db)` wrapper
   fetches `CustomerUsage` + `compute_sentiment_trend` (`health_score_service.py:568`) and calls the core.
3. **Usage-gating (PRD must-have #2 / R4).** Rules needing usage (`silent_churner`, `power_user`, and the
   product-recency arm of `dormant`) **only fire when a `CustomerUsage` row exists**. No usage row →
   those rules are skipped; customer falls through to health/sentiment/recency rules or `unsegmented`.
   Must **never** blanket-label a usage-less org as `dormant`.
4. **Storage.** Nullable `segment` (String) column + index on `customer_health_scores`
   (`models/customer_health.py`). One Alembic migration chained off the **verified** current head
   (`alembic heads` — expected `a5b6c7d8e9f0`; if >1 head, add a `merge heads` first). Backfill existing
   rows in the migration (or leave null + let recompute fill — decide in plan; backfill preferred so the
   feature is populated on deploy).
5. **On-ingest update.** Set `segment` inside `update_customer_health`
   (`health_score_service.py:374-517`) so membership refreshes whenever health is recomputed on ingest.
6. **Nightly recompute task.** `recompute_segments` Celery task (`src/tasks/…`) + beat entry mirroring
   `recompute-usage-scores-daily` (`celery_app.py:194-198`), scheduled ~04:15 UTC (after usage 04:00).
   **Must scan ALL non-archived `CustomerHealth` rows per org** (critique gap #1) so time-based segments
   (`dormant`, `silent_churner`) flip without new activity. Log a per-segment count per org (should-have).

## Out of scope

- List-API filter/column, serializer field, any HTTP surface → `segment-api` aspect.
- Any frontend → `segment-ui` aspect.
- Editable rules, multi-segment tags, targeting hooks.

## Acceptance criteria (testable)

- **Truth table:** unit tests assert `classify_segment` returns the expected slug for a representative row
  per segment, for the priority tiebreaks (e.g. a power-user who is also at_risk → `at_risk`), and for the
  **no-usage-row** path (asserts usage-gated rules don't fire and no false `dormant`).
- **Coverage (PRD G2):** after `recompute_segments`, 100% of non-archived rows have a non-empty segment
  slug or explicit `unsegmented` (integration test over a seeded org).
- **Staleness bound (critique gap #1):** test that a customer with old `last_active_at`/no recent feedback
  is reclassified to `dormant`/`silent_churner` by `recompute_segments` alone (no ingest). ≤24h staleness
  is an accepted property (documented).
- **On-ingest:** ingesting feedback for a customer updates its `segment` via `update_customer_health`.
- **Migration:** `alembic upgrade head` then `downgrade` is clean; `alembic heads` shows a single head after.
- Existing health/usage tests stay green (byte-stable health computation — `segment` write is additive).

## Dependencies & sequencing

- None upstream. Blocks `segment-api` (needs the column) and `segment-ui` (needs the values).
- Verify `alembic heads` FIRST (PRD notes single head `a5b6c7d8e9f0`; don't trust the stale "6 heads").

## Risks

- Thresholds arbitrary (R2) — centralized config, editable-rules deferred. Accept.
- Recompute cost on large orgs — same shape as usage recompute; acceptable. Batch per org.
