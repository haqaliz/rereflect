"""
Idempotent, capped churn-suggestion harvester (harvester-core aspect).

Reads closed-lost CRM records via the injected client, applies
`decide_suggestion` (churn_harvest_core) plus the adapters
(churn_harvest_adapters), and writes `ChurnLabelSuggestion` rows — once.

Never writes `CustomerChurnEvent` — that is review-queue's job on human
confirm (data-model spec, review-queue aspect).

Caller owns the transaction: this function never calls `db.commit()`.
Exception-isolated: any error (including one raised by the injected
`client`) is caught, logged, and returned as `{"status": "error", ...}` —
never propagated. That is what lets the caller wire this into the shipped
CRM enrichment loop without risking a regression there (R4).
"""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError

from src.services.churn_harvest_adapters import (
    hubspot_deal_to_candidate,
    salesforce_opportunity_to_candidate,
)
from src.services.churn_harvest_core import decide_suggestion

logger = logging.getLogger(__name__)

PER_RUN_SUGGESTION_CAP = 200

_ADAPTERS = {
    "hubspot": hubspot_deal_to_candidate,
    "salesforce": salesforce_opportunity_to_candidate,
}


def _fetch_raw_candidates(provider: str, client, company_id: str) -> list[dict]:
    """Provider-specific closed-lost fetch. Exact match on provider name."""
    if provider == "hubspot":
        return client.get_closed_lost_deals_for_company(company_id)
    if provider == "salesforce":
        return client.get_lost_opportunities(company_id)
    return []


def _existing_suggestion_row(db, org_id: int, provider: str, external_opportunity_id: str):
    from src.models import ChurnLabelSuggestion

    return (
        db.query(ChurnLabelSuggestion)
        .filter_by(
            organization_id=org_id,
            provider=provider,
            external_opportunity_id=external_opportunity_id,
        )
        .first()
    )


def _has_active_churn_event(db, org_id: int, customer_email: str) -> bool:
    """Reimplemented locally — the worker cannot import backend-api.

    Mirrors routes/churn_events.py:74-88,148-150:
    org + email + recovered_at IS NULL.
    """
    from src.models import CustomerChurnEvent

    return (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.customer_email == customer_email,
            CustomerChurnEvent.recovered_at.is_(None),
        )
        .first()
        is not None
    )


def _process_raw_record(
    db,
    org_id: int,
    provider: str,
    raw: dict,
    email_lower: str,
    *,
    renewal_set,
    known_emails,
    adapt,
    counters: dict,
    cap: int,
) -> None:
    """
    Decide + write one raw CRM record (deal/opportunity) into a pending
    ChurnLabelSuggestion row, or count it as denied/skipped/dropped.

    Pure move (historical-backfill Phase 1) of harvest_org_suggestions'
    former inline per-candidate loop body — zero logic edits. Shared by the
    forward harvester and the historical backfill so both go through
    exactly one decision+write path (AC-3 — no fork).

    Mutates `counters` in place: scanned/suggested/skipped_existing/denied/
    dropped_by_cap. Never commits (caller owns the transaction).
    """
    from src.models import ChurnLabelSuggestion

    counters["scanned"] += 1

    candidate = adapt(raw, email_lower) if adapt else None
    if candidate is None:
        counters["denied"] += 1
        return

    suggest, _reason = decide_suggestion(
        is_closed=candidate["is_closed"],
        is_won=candidate["is_won"],
        discriminator=candidate["discriminator"],
        renewal_set=renewal_set,
        customer_email=candidate["customer_email"],
        known_emails=known_emails,
    )
    if not suggest:
        counters["denied"] += 1
        return

    if _existing_suggestion_row(
        db, org_id, provider, candidate["external_opportunity_id"]
    ):
        counters["skipped_existing"] += 1
        return

    if _has_active_churn_event(db, org_id, candidate["customer_email"]):
        counters["skipped_existing"] += 1
        return

    if counters["suggested"] >= cap:
        counters["dropped_by_cap"] += 1
        return

    try:
        with db.begin_nested():
            row = ChurnLabelSuggestion(
                organization_id=org_id,
                customer_email=candidate["customer_email"],
                provider=provider,
                external_opportunity_id=candidate["external_opportunity_id"],
                suggested_churned_at=candidate["suggested_churned_at"],
                evidence=candidate["evidence"],
                status="pending",
            )
            db.add(row)
            db.flush()
        counters["suggested"] += 1
    except IntegrityError:
        # Race: another process inserted the same
        # (org, provider, external_opportunity_id) between our
        # pre-check and this flush. The DB UNIQUE constraint is
        # the real guarantee; the pre-check is just the fast path.
        counters["skipped_existing"] += 1


def harvest_org_suggestions(
    org_id: int,
    db,
    client,
    *,
    provider: str,
    renewal_set,
    known_emails,
    company_ids: dict,
    cap: int = PER_RUN_SUGGESTION_CAP,
) -> dict:
    """
    Harvest closed-lost renewal candidates into pending ChurnLabelSuggestion
    rows for one org/provider run.

    Parameters
    ----------
    org_id       : organization ID being harvested
    db           : SQLAlchemy session (caller manages the transaction —
                   this function never commits)
    client       : injected HubSpotClient/SalesforceClient (or Fake in tests)
    provider     : "hubspot" | "salesforce" — selects the fetch + adapter
    renewal_set  : org's configured renewal types/pipelines (frozenset|None)
    known_emails : lowercased set/frozenset of this org's known customer emails
    company_ids  : {customer_email_lower: company_or_account_id} built by the
                   caller's existing enrichment loop
    cap          : per-run cap on new suggestion rows (PER_RUN_SUGGESTION_CAP)

    Returns
    -------
    dict: {status, scanned, suggested, skipped_existing, denied, dropped_by_cap}
    """
    counters = {
        "scanned": 0,
        "suggested": 0,
        "skipped_existing": 0,
        "denied": 0,
        "dropped_by_cap": 0,
    }

    adapt = _ADAPTERS.get(provider)

    try:
        raw_cache: dict[str, list[dict]] = {}

        for email_lower, company_id in sorted(company_ids.items()):
            if company_id not in raw_cache:
                raw_cache[company_id] = _fetch_raw_candidates(provider, client, company_id)
            raw_candidates = raw_cache[company_id]

            for raw in raw_candidates:
                _process_raw_record(
                    db,
                    org_id,
                    provider,
                    raw,
                    email_lower,
                    renewal_set=renewal_set,
                    known_emails=known_emails,
                    adapt=adapt,
                    counters=counters,
                    cap=cap,
                )

        if counters["dropped_by_cap"]:
            # House rule: no silent caps.
            logger.warning(
                "churn_harvest: per-run cap reached org_id=%s provider=%s "
                "cap=%s dropped_by_cap=%s",
                org_id, provider, cap, counters["dropped_by_cap"],
            )

        return {"status": "success", **counters}

    except Exception as exc:
        logger.exception(
            "churn_harvest: unhandled error org_id=%s provider=%s: %s",
            org_id, provider, exc,
        )
        return {"status": "error", **counters}
