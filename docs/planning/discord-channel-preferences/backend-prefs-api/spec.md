# Spec — backend-prefs-api

**Aspect of:** `discord-channel-preferences` · **PRD refs:** R1, R2, R6 (backend half)
**Date:** 2026-08-09

## Problem slice and user outcome

The data model and API must be able to store and round-trip a per-type
`channel_discord` preference (default **True** = opt-out), without a stale client
that PUTs preferences without the new field silently flipping Discord off.

## In-scope requirements

- **Backend model:** `channel_discord` Boolean column on
  `services/backend-api/src/models/user_alert_preference.py` — `nullable=False`,
  `default=True`, `server_default='true'`.
- **Migration:** new file in `services/backend-api/alembic/versions/`, chaining
  onto `8114adde5d96` (current single head), following the
  `d3e4f5g6h7i8_add_channel_intercom_to_alert_prefs.py` pattern
  (`op.add_column('user_alert_preferences', sa.Column('channel_discord', sa.Boolean(), nullable=False, server_default='true'))` + symmetric downgrade).
- **GET /preferences:** `AlertPreferenceItem` gains `channel_discord: bool = True`;
  both construction sites (`routes/notifications.py:354-364` and the injected
  `customer_health_drop` default at `:368-378`) pass `channel_discord=p.channel_discord` /
  `True`.
- **PUT /preferences:** `AlertPreferenceUpdate` gains
  `channel_discord: Optional[bool] = None` with **`None` = leave unchanged**
  (PRD R2 sentinel). In the update loop (`routes/notifications.py:396-416`):
  - existing row: `if item.channel_discord is not None: pref.channel_discord = item.channel_discord`
  - new row: `channel_discord=item.channel_discord if item.channel_discord is not None else True`
  (so a client that omits the field on row creation gets the DB default semantics).

## Out-of-scope boundaries

- No worker changes here (aspect `worker-dispatch`).
- No frontend changes here (aspect `frontend-page`).
- No `channel_intercom` back-fill (that is the worker mirror — this aspect only
  adds `channel_discord` to the backend model).

## Acceptance criteria (testable)

1. `alembic heads` prints exactly one head after the migration.
2. `GET /preferences` returns `channel_discord: true` for every type (including
   the injected `customer_health_drop` default) on a migrated DB.
3. `PUT /preferences` with `channel_discord: false` for a type persists `false`;
   GET returns it.
4. **Absent-field sentinel:** `PUT` a payload that omits `channel_discord` for a
   type whose stored value is `false` → GET still returns `false` (unchanged).
   Same for a stored `true`.
5. `PUT` creating a brand-new row (no DB row for the type) without
   `channel_discord` → GET returns `true`.
6. Backend suite green: `cd services/backend-api && pytest tests/ -v`.

## Dependencies and sequencing notes

- First aspect in the execution order; `worker-dispatch` and `frontend-page`
  depend on this schema/API landing.
- Backend test DB is migrated fresh in CI — the migration must be self-contained.

## Open questions or risks

- None blocking. Note: the `channel_intercom` worker-mirror divergence (pre-existing
  drift) is fixed in `worker-dispatch`, not here.
