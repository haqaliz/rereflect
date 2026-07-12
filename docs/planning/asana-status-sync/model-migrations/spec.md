# Aspect: model-migrations

## Problem slice & outcome
Add the durable state that inbound status-sync reads and writes: the per-org opt-in flag + mapping on
`AsanaIntegration`, and per-link sync state on `FeedbackAsanaTask`. Without these columns nothing else
can be built. Mirror the Jira columns exactly.

## In scope
- **`asana_integrations`** (backend `models/asana_integration.py` + worker mirror
  `worker-service/src/models/__init__.py`):
  - `status_sync_enabled` — `Boolean`, `nullable=False`, `default=False`, `server_default=sa.false()`.
  - `status_mapping` — `JSON`, `nullable=True`.
  - Reuse existing `last_synced_at` / `last_sync_status` / `last_error` (no new columns).
- **`feedback_asana_tasks`** (backend + worker mirror):
  - `asana_completed` — `Boolean`, nullable.
  - `asana_status_category` — `String(20)`, nullable (holds `new`/`done`; forward-compat for
    `indeterminate`).
  - `last_status_synced_at` — `DateTime`, nullable.
- **One Alembic migration** under `services/backend-api/alembic/versions/` adding all five columns,
  with a working `downgrade()` that drops them.
- Worker mirror models updated in lockstep (no FKs, minimal columns — match the `JiraIntegration` /
  `FeedbackJiraIssue` worker-mirror pattern).

## Out of scope
- Any route, task, or client logic (later aspects).
- Backfilling existing rows (new columns default NULL/false — that IS the seed baseline).

## Acceptance criteria (testable)
- `alembic upgrade head` then `downgrade -1` round-trips cleanly (mirror
  `test_jira_status_sync_migration.py`).
- New migration's `down_revision` == the **current single head** (verify with `alembic heads`; there
  must be exactly one head after this migration).
- Backend model exposes the 5 new attributes with the specified types/defaults; a row created without
  them defaults `status_sync_enabled=False`, others NULL.
- Worker mirror model exposes the same columns (read/write) and its own Fernet `_decrypt` still works.
- Model unit tests assert defaults + nullability (extend `test_asana_models.py`).

## Dependencies & sequencing
- **First.** Everything else depends on these columns.
- Verify the current alembic head BEFORE writing the migration (repo has a documented multi-head
  gotcha; the Jira status-sync migration had to correct a stale down_revision).

## Open questions / risks
- Confirm single head at implementation time; if multiple heads exist, resolve/merge first.
- `status_mapping` stored as `JSON` (portable) consistent with Jira's column type.
