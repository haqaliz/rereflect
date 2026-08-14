# Aspect spec — DB config & model changes

**Feature:** `intercom-writeback` (prd.md R1 + R4) · **Aspect:** `db-config-model`

## Problem slice

The write-back needs a per-org opt-in switch with honest status readout (R1) and a
durable per-feedback idempotency marker (R4). Nothing exists today: the token-paste
`IntercomIntegration` row carries sync columns but no writeback columns, and
`feedback_items` has no marker.

## In-scope

- Backend `IntercomIntegration` (`services/backend-api/src/models/intercom_integration.py`)
  gains: `writeback_enabled` (Boolean, not null, default `false`, `server_default="false"`),
  `writeback_action` (String(32), not null, default `"note_and_close"`),
  `last_writeback_at` (timestamptz, nullable), `last_writeback_status` (String(64),
  nullable), `last_writeback_error` (Text, nullable) — the CRM writeback column set
  (`hubspot_integration.py:39-44` precedent).
- Backend `FeedbackItem` (`services/backend-api/src/models/feedback.py`) gains
  `intercom_writeback_at` (timestamptz, nullable).
- One Alembic migration chained off the current single head `3cb9a0d1456b` (CI asserts
  exactly one head). Alembic model metadata (`alembic/env.py` or equivalent) must include
  both tables as it does today.
- Worker mirrors in `services/worker-service/src/models/__init__.py` for both
  `IntercomIntegration` (writeback columns) and `FeedbackItem`
  (`intercom_writeback_at`), following the existing mirror conventions.
- Parity: extend the column-parity test so worker/backend columns match (precedent:
  `worker-service/tests/test_intercom_tenancy_discriminator.py::TestModelParity`).

## Out of scope

- Any Redis key/scheme for idempotency (the marker is DB-durable by design).
- Configurable target status (`closed`) — v1 pins `resolved` (prd.md OQ1).
- Backfill-on-enable (prd.md OQ2).

## Acceptance criteria (testable)

1. `alembic heads` prints exactly one head; the migration chains off `3cb9a0d1456b`.
2. Backend model columns exist with the defaults above (new rows: `writeback_enabled=false`,
   `writeback_action="note_and_close"`); `intercom_writeback_at` null by default.
3. Migration is upgrade/downgrade-safe (downgrade drops exactly the new columns).
4. Worker mirror parity test passes (worker columns match backend, including types).
5. Full backend + worker suites green with the migration applied to a clean DB.

## Dependencies & sequencing

- First aspect: every other aspect reads the new columns / marker.
- No dependency on other aspects.

## Open questions / risks

- Alembic model import list: confirm both models are registered for autogenerate (or
  write the migration by hand — the house style has done both; match the latest
  migration `3cb9a0d1456b`).
