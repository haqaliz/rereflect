# Aspect: asana-client-get-task

## Problem slice & outcome
The reconcile core needs each linked Asana task's current completion state. Today `AsanaClient` can
only create tasks. Add a read method (backend + a worker copy), so the poller has something to read.

## In scope
- **Backend `AsanaClient.get_task(task_gid)`** (`services/backend-api/src/services/asana_client.py`):
  - `GET /tasks/{gid}?opt_fields=completed,completed_at,memberships.section.name`.
  - Returns `{"completed": bool, "completed_at": str|None, "memberships": list}` (parsed from
    `resp.json()["data"]`).
  - Reuses the existing error taxonomy (`AsanaAuthError` 401/403, `AsanaTransientError` 429/≥500,
    `AsanaNotFoundError` 404) and the fixed-host `app.asana.com` invariant.
- **Worker `AsanaClient` copy** under `services/worker-service/src/clients/asana.py` (mirror
  `worker-service/src/clients/jira.py`), scoped to `get_task` only:
  - Same auth/host invariant, same error classes.
  - **Adds `Retry-After` handling on 429**: read `int(headers.get("Retry-After", "10"))`,
    `time.sleep(retry_after)`, then raise `AsanaTransientError` (the Celery task retries on it). This is
    the one behavior the backend client lacks.
- A small pure adapter mapping task state → category:
  `asana_category(completed: bool) -> "done" | "new"` (`completed=True → "done"`, else `"new"`). Keep
  it a standalone function (unit-testable, no I/O). Section/custom-field → `indeterminate` is v2.

## Out of scope
- Batch fetch (Asana has no `in(...)`); one GET per gid is intentional for slice 1.
- Section-name interpretation (v2) — `memberships` is fetched but not yet used for category.
- Any Celery/DB code (worker-sync-task aspect).

## Acceptance criteria (testable)
- Backend `get_task` returns the parsed dict on 200; raises the correct typed error on 401/403/404/429/5xx
  (extend `test_asana_client.py`).
- Worker client `get_task` on a 429 with `Retry-After: N` sleeps ~N then raises `AsanaTransientError`
  (mirror `test_jira_client_worker.py`; patch `time.sleep`).
- `asana_category(True) == "done"`, `asana_category(False) == "new"` (pure unit test).
- Token never appears in `repr`/`str`/logs.

## Dependencies & sequencing
- Independent of model-migrations for its own tests, but the worker-sync-task aspect depends on this.
- Can be built in parallel with model-migrations.

## Open questions / risks
- Confirm Asana returns `completed_at` under `opt_fields`; if absent for incomplete tasks it's simply
  `None`.
