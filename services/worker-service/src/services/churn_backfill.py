"""
Cancellable, window-bounded historical CRM churn-suggestion backfill
(historical-backfill aspect).

Why this exists: forward-only harvesting (churn_suggestion_harvester) reads
only the CRM records visible from today's contact/company snapshot going
forward, at ~200 suggestions/run. The volume that makes the 500-label
readiness gate reachable lives in the CRM's *history* — years of already
closed-lost renewals. This module pages back over an operator-chosen window
(default 24 months, hard max 60) to land that history in the review queue
in one bounded, resumable pass.

MUST NOT fork the decision+write path: every raw record goes through
`churn_suggestion_harvester._process_raw_record` — the exact same
default-deny rule, adapters, idempotency (UNIQUE org+provider+ext_id), and
active-churn-event suppression as the forward harvester. This module only
changes *which pages are read* (a `since` floor passed to the Phase 2
window-bounded client accessors) — never the suggestion logic itself.

Never writes CustomerChurnEvent — suggestions only, human-gated via the
review queue (M5). Caller owns the transaction: never calls db.commit().

Celery-free and cancellable: `should_abort` is polled once per "fetch
unit" (one company/account), the finest boundary this module controls —
paging itself lives inside the shipped HubSpot/Salesforce clients (Phase 2)
and is not forked to expose a finer boundary (R4). `throttle` is invoked
between fetch units so a multi-year page-through cannot exhaust the org's
CRM API quota.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, Optional

from dateutil.relativedelta import relativedelta

from src.services.churn_suggestion_harvester import _ADAPTERS, _process_raw_record

logger = logging.getLogger(__name__)

DEFAULT_BACKFILL_MONTHS = 24
MAX_BACKFILL_MONTHS = 60

# A multi-year pass surfaces far more eligible history than a daily forward
# run — the daily PER_RUN_SUGGESTION_CAP (200) would silently truncate most
# of it. Sized for a one-off, bounded, human-reviewed backfill.
BACKFILL_SUGGESTION_CAP = 2000

# Sleep between fetch units (companies/accounts), not between HTTP pages
# (those are already throttled/retried inside the Phase 2 clients). Keeps a
# multi-year page-through from bursting the org's CRM API quota.
BACKFILL_THROTTLE_SECONDS = 0.2


def _fetch_raw_since(provider: str, client, company_id: str, since: datetime) -> list[dict]:
    """Provider-specific closed-lost fetch, window-bounded by `since`.

    Exact match on provider name — mirrors
    churn_suggestion_harvester._fetch_raw_candidates, but calls the Phase 2
    since-floor accessors instead of the unbounded ones.
    """
    if provider == "hubspot":
        return client.get_closed_lost_deals_for_company(company_id, since=since)
    if provider == "salesforce":
        return client.get_lost_opportunities(company_id, since=since)
    return []


def run_backfill(
    org_id: int,
    db,
    client,
    *,
    provider: str,
    renewal_set,
    known_emails,
    company_ids: dict,
    months: int = DEFAULT_BACKFILL_MONTHS,
    cap: int = BACKFILL_SUGGESTION_CAP,
    should_abort: Callable[[], bool] = lambda: False,
    throttle: Callable[[float], None] = time.sleep,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Backfill closed-lost renewal candidates from `months` back into pending
    ChurnLabelSuggestion rows for one org/provider run.

    Parameters
    ----------
    org_id       : organization ID being backfilled
    db           : SQLAlchemy session (caller manages the transaction —
                   this function never commits)
    client       : injected HubSpotClient/SalesforceClient (or Fake in tests)
    provider     : "hubspot" | "salesforce" — selects the fetch + adapter
    renewal_set  : org's configured renewal types/pipelines (frozenset|None)
    known_emails : lowercased set/frozenset of this org's known customer emails
    company_ids  : {customer_email_lower: company_or_account_id} built by the
                   caller the same way as the forward sync's enrichment loop
    months       : window size in months back from now (DEFAULT_BACKFILL_MONTHS,
                   caller enforces the [1, MAX_BACKFILL_MONTHS] bound at the API layer)
    cap          : per-run cap on new suggestion rows (BACKFILL_SUGGESTION_CAP)
    should_abort : polled once before each fetch unit (company/account); a
                   True mid-run returns immediately with status "cancelled"
                   and the counters accumulated so far (partial progress —
                   safe to re-run, idempotent via the DB UNIQUE constraint)
    throttle     : called between fetch units (default time.sleep) to avoid
                   bursting the org's CRM API quota over a multi-year pass
    on_progress  : optional callback invoked with a copy of the running
                   counters after each fetch unit, so the caller (task) can
                   persist live progress for resumability

    Returns
    -------
    dict: {status: "success"|"cancelled", since (ISO string),
           scanned, suggested, skipped_existing, denied, dropped_by_cap}

    Never writes CustomerChurnEvent.
    """
    since = datetime.utcnow() - relativedelta(months=months)

    counters = {
        "scanned": 0,
        "suggested": 0,
        "skipped_existing": 0,
        "denied": 0,
        "dropped_by_cap": 0,
    }

    adapt = _ADAPTERS.get(provider)
    raw_cache: dict[str, list[dict]] = {}

    for email_lower, company_id in sorted(company_ids.items()):
        if should_abort():
            return {"status": "cancelled", "since": since.isoformat(), **counters}

        if company_id not in raw_cache:
            raw_cache[company_id] = _fetch_raw_since(provider, client, company_id, since)
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

        if on_progress is not None:
            on_progress(dict(counters))

        throttle(BACKFILL_THROTTLE_SECONDS)

    if counters["dropped_by_cap"]:
        # House rule: no silent caps — name the count AND the covered window.
        logger.warning(
            "churn_backfill: per-run cap reached org_id=%s provider=%s cap=%s "
            "dropped_by_cap=%s since=%s months=%s",
            org_id, provider, cap, counters["dropped_by_cap"], since.isoformat(), months,
        )

    return {"status": "success", "since": since.isoformat(), **counters}
