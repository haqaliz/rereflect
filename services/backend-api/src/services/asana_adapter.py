"""Pure Asana task-state -> status_sync_core category adapter (no I/O).

Verbatim mirror of the worker-owned
services/worker-service/src/services/asana_adapter.py (backend-api cannot
import the worker service — see status_sync_core.py's module docstring for
the same duplication rationale). Used by the asana-webhook receiver's
reconcile port (src/services/asana_status_reconcile.py) to translate a
freshly-observed `completed` bool into a status_sync_core category key,
exactly like the poller does.

Slice 1 maps only the boolean `completed` field:
  completed True  -> "done"  (status_sync_core resolves -> resolved by default)
  completed False -> "new"
Section-name / custom-field -> "indeterminate" is deferred to v2 (explicitly
out of scope for the asana-webhook aspect too — see spec.md).
"""
from __future__ import annotations


def asana_category(completed: bool) -> str:
    """Return the status_sync_core category key for an Asana task's completion."""
    return "done" if completed else "new"
