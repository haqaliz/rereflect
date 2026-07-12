"""Pure Asana task-state -> status_sync_core category adapter (no I/O).

Slice 1 maps only the boolean `completed` field:
  completed True  -> "done"  (status_sync_core resolves -> resolved by default)
  completed False -> "new"
Section-name / custom-field -> "indeterminate" is deferred to v2; `memberships`
is fetched by AsanaClient.get_task but intentionally not consulted here yet.
"""
from __future__ import annotations


def asana_category(completed: bool) -> str:
    """Return the status_sync_core category key for an Asana task's completion."""
    return "done" if completed else "new"
