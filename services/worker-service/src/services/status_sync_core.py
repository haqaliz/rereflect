"""
Pure, no-I/O reconcile core for inbound Jira status sync.

This module MUST NOT import FastAPI, SQLAlchemy, or any DB/network client.
It is copied verbatim into the worker service (see
services/worker-service/src/services/status_sync_core.py) so it must remain
pure Python with zero external dependencies beyond the standard library.
"""
from __future__ import annotations

VALID_STATUSES = ("new", "in_review", "resolved", "closed")

DEFAULT_CATEGORY_MAP = {
    "done": "resolved",
    "indeterminate": "in_review",
    "new": "new",
}

CATEGORY_RANK = {"new": 0, "indeterminate": 1, "done": 2}


def resolve_target_status(category: str, mapping: dict | None) -> str | None:
    """Resolve a Jira status category to a Rereflect workflow_status.

    `mapping` (a JSON dict, possibly partial or None) overrides
    DEFAULT_CATEGORY_MAP on a per-category-key basis. Returns None when the
    category is unknown, or when the resolved target status is not one of
    VALID_STATUSES.
    """
    if category not in DEFAULT_CATEGORY_MAP:
        return None

    merged = dict(DEFAULT_CATEGORY_MAP)
    if mapping:
        merged.update(mapping)

    target = merged.get(category)
    if target is None:
        return None
    if target not in VALID_STATUSES:
        return None
    return target


def is_seed(stored_category: str | None) -> bool:
    """True when this is the first observation of a link (no stored category yet)."""
    return stored_category is None


def most_advanced(categories: list[str]) -> str | None:
    """Return the category with the highest CATEGORY_RANK among `categories`.

    Unknown categories are ignored. Returns None if the input is empty or
    contains no known categories.
    """
    known = [c for c in categories if c in CATEGORY_RANK]
    if not known:
        return None
    return max(known, key=lambda c: CATEGORY_RANK[c])


def decide_link_update(
    fetched_category: str, fetched_name: str, stored_category: str | None
) -> tuple[str, str, str]:
    """Decide what to do with a freshly-fetched Jira link status.

    Returns (action, fetched_name, fetched_category) where action is:
      - 'seed'    when stored_category is None (first observation)
      - 'noop'    when fetched_category == stored_category
      - 'changed' when stored_category is not None and differs from fetched
    """
    if is_seed(stored_category):
        action = "seed"
    elif fetched_category == stored_category:
        action = "noop"
    else:
        action = "changed"
    return (action, fetched_name, fetched_category)
