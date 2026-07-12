"""
Pure, no-I/O reconcile core for inbound Zendesk status sync.

This module MUST NOT import FastAPI, SQLAlchemy, or any DB/network client.
It is copied verbatim into the worker service (see
services/worker-service/src/services/zendesk_status_core.py) so it must
remain pure Python with zero external dependencies beyond the standard
library and status_sync_core.VALID_STATUSES.
"""
from __future__ import annotations

from src.services.status_sync_core import VALID_STATUSES

ZENDESK_STATUSES = ("new", "open", "pending", "hold", "solved", "closed")

DEFAULT_ZENDESK_MAP = {
    "new": "new",
    "open": "in_review",
    "pending": "in_review",
    "hold": "in_review",
    "solved": "resolved",
    "closed": "closed",
}


def resolve_target_status(zendesk_status: str, mapping: dict | None) -> str | None:
    """Resolve a Zendesk ticket status to a Rereflect workflow_status.

    `mapping` (a JSON dict, possibly partial or None) overrides
    DEFAULT_ZENDESK_MAP on a per-status-key basis. Returns None when the
    zendesk_status is unknown, or when the resolved target status is not
    one of VALID_STATUSES.
    """
    merged = {**DEFAULT_ZENDESK_MAP, **(mapping or {})}
    target = merged.get(zendesk_status)
    return target if target in VALID_STATUSES else None


def decide_update(fetched_status: str, stored_status: str | None) -> str:
    """Decide what to do with a freshly-fetched Zendesk ticket status.

    Returns:
      - 'seed'    when stored_status is None (first observation)
      - 'noop'    when fetched_status == stored_status
      - 'changed' when stored_status is not None and differs from fetched
    """
    if stored_status is None:
        return "seed"
    if fetched_status == stored_status:
        return "noop"
    return "changed"
