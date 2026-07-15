"""
Pure, no-I/O decision core for CRM lost-renewal churn suggestions.

This module MUST NOT import Celery, SQLAlchemy, FastAPI, httpx, or any CRM
client. Mirrors the purity contract of status_sync_core.py — worker-service
only (see spec.md §6: no backend mirror, extract-on-second-use).

DEFAULT-DENY: `decide_suggestion` only suggests when every condition holds;
any None/unknown/unconfigured input denies. Never raises.
"""
from __future__ import annotations

# Fixed, asserted deny order — a reorder is a breaking change to the logged
# reason. Checked in this exact order so the logged reason is deterministic.
SUGGESTION_DENY_REASONS = (
    "not_closed",
    "won",
    "discriminator_not_configured",
    "no_discriminator",
    "unknown_customer",
)


def decide_suggestion(
    *,
    is_closed: bool,
    is_won: bool,
    discriminator: str | None,
    renewal_set: frozenset[str] | None,
    customer_email: str | None,
    known_emails: frozenset[str],
) -> tuple[bool, str | None]:
    """(suggest, deny_reason). DEFAULT-DENY. Never raises.

    Suggest only when closed AND not won AND `discriminator in renewal_set`
    AND `customer_email in known_emails`. Matching is exact — no regex, no
    normalization, no prefix match (M2).
    """
    if not is_closed:
        return False, "not_closed"
    if is_won:
        return False, "won"
    if not renewal_set:
        return False, "discriminator_not_configured"
    if not discriminator:
        return False, "no_discriminator"
    if discriminator not in renewal_set:
        return False, "no_discriminator"
    if not customer_email or customer_email not in known_emails:
        return False, "unknown_customer"

    return True, None
