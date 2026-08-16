# Aspect spec — Column, migration, mirrors, status API

**Feature:** `intercom-backlog-drain-visibility` (prd.md R3 + R4) · **Aspect:** `db-status-api`

## Problem slice

The estimate needs storage (one nullable column), a migration off the single head, both
model mirrors with the parity type-tuple fix, and a status-API field so the frontend
can render it.

## In-scope

- Backend `IntercomIntegration` (`services/backend-api/src/models/intercom_integration.py`):
  `backlog_remaining = Column(Integer, nullable=True)` after the sync-status block
  (:69-71).
- Hand-written migration chained off the single head `e4f5a6b7c8d9`, mirroring the
  `e4f5a6b7c8d9_add_intercom_writeback_columns.py` style (docstring manifest,
  add/drop, downgrade drops exactly the new column) + the migration-test pattern
  (`test_intercom_writeback_columns_migration.py`).
- Worker mirror in `services/worker-service/src/models/__init__.py` (:1282-1284 area,
  no `server_default` — house convention).
- **Parity fix:** add `"backlog_remaining"` to `WRITEBACK_INTEGRATION_COLUMNS`
  (test_intercom_tenancy_discriminator.py:324-331) so the type-parity test covers it
  (Integer vs BigInteger drift caught). Name-parity passes automatically once both
  models have the column.
- Status API: `IntercomStatusResponse.backlog_remaining: Optional[int] = None`
  (intercom_integration.py:139-161, after `feedback_items_ingested` :155);
  `_build_status_response` maps `row.backlog_remaining` (between :291 and :292);
  disconnected/absent keeps the default (the `IntercomStatusResponse(connected=False)`
  shape at :450 unchanged).
- Tests: migration upgrade/downgrade + single head; model parity (names + types);
  status characterization extended — `test_intercom_writeback_config.py`
  `TestWritebackStatusExtension` byte-identical loop is additive-safe; add explicit
  `backlog_remaining` assertions (connected row with value, null default, disconnected
  default).

## Out of scope

- Client/sync (other aspects); frontend rendering.

## Acceptance criteria (testable)

1. `alembic heads` prints exactly one head (off `e4f5a6b7c8d9`); upgrade/downgrade
   round-trip drops only the new column.
2. Parity tests green with the column in BOTH models + the type tuple.
3. GET /status returns `backlog_remaining` (value/null); disconnected → `None`; the
   byte-identical characterization loop still passes (additive).
4. Backend suite green.

## Dependencies & sequencing

- Independent of client/sync aspects (model + route only); before the frontend aspect.

## Open questions / risks

- Nullable int vs NOT NULL + server_default 0: nullable chosen (estimate has no
  meaningful 0 until a run completes; null = "no estimate").
