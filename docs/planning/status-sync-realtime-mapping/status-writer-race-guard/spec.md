# Aspect spec — `status-writer-race-guard`

Part of PRD `status-sync-realtime-mapping`. Prereq for the webhook aspects'
apply path.

## Problem slice & user outcome
Concurrent status applies (15-min poll + a new real-time webhook, or two
overlapping poll runs) must never double-write a `FeedbackWorkflowEvent` or
clobber a newer status. Today the shared worker applier is not race-safe.

## Verified current state
`worker-service/src/services/status_writer.py::apply_status_change_worker` does
an **in-Python read-modify-write**:
```python
if feedback.workflow_status == new_status:
    return False
old_status = feedback.workflow_status
feedback.workflow_status = new_status
# ... db.add(FeedbackWorkflowEvent(...))
```
This is NOT the race-safe pattern Zendesk uses in
`backend-api/src/services/zendesk_status_reconcile.py::_apply_zendesk_status`,
which does a conditional `UPDATE feedback_items SET workflow_status=:new WHERE
id=:id AND organization_id=:org AND workflow_status=:old` and writes the event
**only if 1 row changed**. Under concurrency two callers can both read the same
`old_status`, both pass the equality check, and both write an event / one
clobbers the other.

## In scope
- Rewrite `apply_status_change_worker` to use a conditional UPDATE guarded on the
  observed `old_status` (dialect-agnostic; works on PostgreSQL + SQLite as the
  Zendesk path does). Write exactly one event iff the UPDATE affected 1 row;
  return False + write nothing otherwise. Preserve the existing signature
  (`actor_label`, `metadata`), `actor_id=None`, `event_type="status_changed"`,
  and the "no outbound webhook" invariant.
- The caller must pass the `old_status` it observed (the sidecar/link's last
  value) so the guard is meaningful. Update `jira_sync.py` / `asana_sync.py`
  call sites accordingly (they already know the prior status via the link's
  `*_status_category` / sidecar).
- Backend-api reconcile port for the webhook path (added in the webhook aspects)
  MUST reuse the same guard — factor it so both share the SQL, or mirror it
  verbatim like Zendesk (worker can't import backend-api).

## Out of scope
- Outbound webhooks. Mapping semantics. Any provider-specific logic (this stays
  provider-agnostic).

## Acceptance criteria (testable)
- Characterization first: existing `tests/test_jira_sync_task.py` /
  `test_asana_sync_task.py` stay green (same event counts) — behavior preserved
  for the non-concurrent path.
- New regression test: simulate a stale apply (feedback already at the new
  status via a concurrent update) → applier writes **zero** events and returns
  False. Simulate the happy path → exactly one event, status updated.
- No-op on equal status: zero events (unchanged behavior).

## Dependencies & sequencing
- Independent of `mapping-editor`. **Must land before** `jira-webhook` /
  `asana-webhook` merge, since their synchronous apply reuses this guard.

## Open questions / risks
- Whether to keep `apply_status_change_worker` as an ORM-level conditional or a
  Core `text()` UPDATE (Zendesk uses `text()`). Prefer matching Zendesk for
  consistency and to avoid ORM identity-map staleness.
- Ensure the single duplicated `status_sync_core.py` is untouched here (this is
  the *writer*, not the mapper).
