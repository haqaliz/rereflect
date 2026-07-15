"""
Pure, no-I/O adapters normalizing a HubSpot deal / Salesforce Opportunity to
one churn-suggestion candidate shape (harvester-core aspect).

This module MUST NOT import Celery, SQLAlchemy, FastAPI, httpx, or any CRM
client — worker-service only (spec.md §6: no backend mirror,
extract-on-second-use).

Both adapters return a dict with identical keys, or None when the record
lacks an id or a usable close date:
  {customer_email, external_opportunity_id, suggested_churned_at, evidence,
   is_closed, is_won, discriminator}

`suggested_churned_at` is always the CRM close date (never "now") — stable
across calls, which is what makes re-harvest idempotent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

_HS_CLOSED_STAGES = {"closedwon", "closedlost"}


def _parse_close_date(raw: object) -> Optional[datetime]:
    """Reuse of hubspot_sync.py:239-244's ISO-8601 parse (Z -> +00:00)."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_amount(raw: object) -> Optional[float]:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def hubspot_deal_to_candidate(deal: dict, contact_email: str) -> Optional[dict]:
    """Normalize a HubSpot deal (closedlost) into a candidate, or None."""
    external_opportunity_id = deal.get("id")
    if not external_opportunity_id:
        return None

    props = deal.get("properties", {}) or {}

    suggested_churned_at = _parse_close_date(props.get("closedate"))
    if suggested_churned_at is None:
        return None

    stage = props.get("dealstage")
    is_closed = stage in _HS_CLOSED_STAGES
    is_won = stage == "closedwon"
    discriminator = props.get("pipeline")

    evidence = {
        "name": props.get("dealname"),
        "stage": stage,
        "type": props.get("pipeline"),
        "amount": _parse_amount(props.get("amount")),
        "close_date": props.get("closedate"),
        "provider": "hubspot",
    }

    return {
        "customer_email": contact_email.lower(),
        "external_opportunity_id": external_opportunity_id,
        "suggested_churned_at": suggested_churned_at,
        "evidence": evidence,
        "is_closed": is_closed,
        "is_won": is_won,
        "discriminator": discriminator,
    }


def salesforce_opportunity_to_candidate(opp: dict, contact_email: str) -> Optional[dict]:
    """Normalize a Salesforce Opportunity (closed-lost) into a candidate, or None."""
    external_opportunity_id = opp.get("Id")
    if not external_opportunity_id:
        return None

    suggested_churned_at = _parse_close_date(opp.get("CloseDate"))
    if suggested_churned_at is None:
        return None

    discriminator = opp.get("Type")

    evidence = {
        "name": opp.get("Name"),
        "stage": opp.get("StageName"),
        "type": opp.get("Type"),
        "amount": _parse_amount(opp.get("Amount")),
        "close_date": opp.get("CloseDate"),
        "provider": "salesforce",
    }

    return {
        "customer_email": contact_email.lower(),
        "external_opportunity_id": external_opportunity_id,
        "suggested_churned_at": suggested_churned_at,
        "evidence": evidence,
        "is_closed": bool(opp.get("IsClosed")),
        "is_won": bool(opp.get("IsWon")),
        "discriminator": discriminator,
    }
