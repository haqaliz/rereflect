"""
Pydantic schemas for the product-usage ingest endpoint.

POST /api/v1/webhooks/usage accepts a Segment-compatible batch body.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# 16 KB limit for per-event properties
_PROPERTIES_MAX_BYTES = 16 * 1024


class UsageEventIn(BaseModel):
    """A single inbound usage event (Segment-compatible normalized shape)."""

    type: Literal["identify", "track"] = Field(
        ..., description="Event type: 'identify' or 'track'"
    )
    email: Optional[str] = None
    userId: Optional[str] = None
    event: Optional[str] = None       # track: event name (e.g. "login")
    name: Optional[str] = None        # identify/track: display name
    timestamp: Optional[datetime] = None
    messageId: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    traits: dict[str, Any] = Field(default_factory=dict)


class UsageBatchIn(BaseModel):
    """Normalized batch body: up to 1000 events per request."""

    events: list[UsageEventIn] = Field(
        ...,
        description="List of usage events (max 1000 per request)",
    )


class UsageIngestResponse(BaseModel):
    """Response body for POST /api/v1/webhooks/usage."""

    accepted: int
    skipped: int
    skipped_reasons: dict[str, int] = Field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_email(event: UsageEventIn) -> Optional[str]:
    """Return the customer email from ``email`` field or ``traits.email``, else None."""
    if event.email:
        return event.email
    return event.traits.get("email") or None


def guard_properties(props: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Ensure serialized properties stay within the 16 KB limit.

    Returns:
        (properties, was_truncated) — if ``was_truncated`` is True the original
        payload exceeded the limit and has been replaced with an empty dict.
    """
    serialized = json.dumps(props, default=str)
    if len(serialized.encode()) > _PROPERTIES_MAX_BYTES:
        return {}, True
    return props, False
