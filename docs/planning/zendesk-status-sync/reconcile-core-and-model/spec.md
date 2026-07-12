# Aspect: reconcile-core-and-model

**Slug:** `zendesk-status-sync` · **Aspect dir:** `reconcile-core-and-model`
**Sequencing:** FIRST — foundation for poll-task, webhook-realtime, backend-routes.

## Problem slice & outcome

The pure, I/O-free heart of Zendesk status-sync: map a Zendesk ticket status → Rereflect
`workflow_status`, decide seed/noop/changed against the last-observed status, and the persistence
sidecar that remembers last-observed status per feedback. No HTTP, no Celery, no DB writes in the
pure function.

## In scope

1. **Zendesk reconcile module** (worker + backend mirrors, e.g. `src/services/zendesk_status_core.py`):
   - `ZENDESK_STATUSES = ("new","open","pending","hold","solved","closed")`
   - `DEFAULT_ZENDESK_MAP = {"new":"new","open":"in_review","pending":"in_review","hold":"in_review","solved":"resolved","closed":"closed"}`
   - `resolve_target_status(zendesk_status, mapping|None) -> str|None` — merges DEFAULT with per-org override (partial allowed); returns None if status unknown or target ∉ `VALID_STATUSES`. Reuse `VALID_STATUSES` from `status_sync_core`.
   - `decide_update(fetched_status, stored_status|None) -> ("seed"|"noop"|"changed")` — `seed` when `stored_status is None`; `noop` when `fetched == stored`; else `changed`.
   - **Do NOT modify `status_sync_core.py`** (Jira constants stay byte-identical).
2. **Sidecar model** `FeedbackZendeskSync` in BOTH mirrors (`backend-api/src/models/…`, `worker-service/src/models/__init__.py`):
   - `feedback_id` (FK feedback.id, CASCADE, PRIMARY KEY), `last_ticket_status` (String(20), not null), `last_status_synced_at` (DateTime, not null).
3. **Integration columns** on `ZendeskIntegration` (BOTH mirrors): `status_sync_enabled` (Bool, not null, server_default false), `status_mapping` (JSON, null), `last_status_synced_at` (DateTime, null), `last_status_sync_error` (Text, null).
4. **Alembic migration** — new revision, `down_revision="c4d5e6f7a8b9"`: add the 4 integration columns + create `feedback_zendesk_sync`. Provide `downgrade()`.

## Out of scope
- Any HTTP fetch (client aspect), Celery task (poll aspect), route/webhook wiring, apply-to-feedback writer.

## Acceptance criteria (testable)
- `resolve_target_status("solved", None) == "resolved"`; `"closed"→"closed"`; `"open"/"pending"/"hold"→"in_review"`; `"new"→"new"`.
- Override `{"closed":"resolved"}` makes `resolve_target_status("closed", {"closed":"resolved"}) == "resolved"`; unknown status → None; bad target (`{"open":"bogus"}`) → None.
- `decide_update("open", None) == "seed"`; `decide_update("open","open") == "noop"`; `decide_update("solved","open") == "changed"`.
- Characterization test: `status_sync_core.py` (Jira) unchanged — import + Jira constants assert equal to committed values.
- `alembic upgrade head` then `downgrade -1` round-trips cleanly on a scratch DB; single head preserved.
- Model-parity test (existing pattern) passes for the new columns/table across both mirrors.

## Dependencies & sequencing
- None upstream. Blocks: poll-task, webhook-realtime, backend-routes.

## Open questions / risks
- Confirm `String(20)` fits all Zendesk status names (longest = `pending`, 7 chars) — safe.
- Sidecar CASCADE-deletes with feedback (feedback delete already archives health rows) — verify no FK conflict.
