"""
Usage-decline churn-label detector (worker-detector aspect).

Wires the pure `usage_decline_labels_core` functions to the worker's real
CustomerUsage / CustomerUsageHistory / OrgAIConfig rows.

**Placement (documented, wired in Phase 5 —
`test_usage_decline_detector_seam.py` / `usage_metrics.py`):** this module's
`detect_usage_decline_labels` is invoked from `recompute_usage_scores`
STRICTLY AFTER the daily snapshot commit (`usage_metrics.py:693-694`), never
at the M3.2c post-commit drain seam (`:667-681`) — the spec's original
placement note was wrong; see
`docs/planning/usage-decline-churn-labels/worker-detector/plan_20260723.md`
section 1. Today's snapshot row does not exist until that final commit, so a
detector run before it would read history missing the current day.

This file implements Phases 1-4 of that plan: the detector skeleton + the
off/shadow/active mode gate (Phase 1), a batched, org-scoped (never
per-customer) history load (Phase 2), the M3b population-level outage guard
(Phase 3) — computed and enforced BEFORE any write path exists — and the
`active`-mode write path (Phase 4): qualifying customers become pending
`ChurnLabelSuggestion` rows, idempotently, with the CRM harvester's denial
semantics reimplemented locally (never imported from
`churn_suggestion_harvester.py` — that module is the CRM path and is never
edited or imported from here, per the plan's "reuse by copying" directive).

Hard fences (never touched by this module): churn_risk_component,
churn_probability, churn_probability_low/high, calibration_model_id,
time_to_churn_bucket, classify_usage_trend, select_nearest_in_band_snapshot,
apply_trend_penalty, churn_suggestion_harvester.py, churn_harvest_core.py.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from src.services.usage_decline_labels_core import (
    build_evidence,
    outage_suspected,
    qualifying_streak,
    suggestion_key,
)

logger = logging.getLogger(__name__)

# usage_churn_label_config default when NULL or the key is absent/falsy
# (PRD M2).
DEFAULT_SUSTAIN_DAYS = 7

# ChurnLabelSuggestion.provider value written by this detector — distinct
# from the CRM harvester's "hubspot"/"salesforce" values.
PROVIDER = "usage_decline"

# Per-run cap on new ChurnLabelSuggestion rows written per org, per call
# (house rule: no silent caps — anything dropped is logged, see
# `dropped_by_cap` below). Deliberately smaller than the CRM harvester's
# PER_RUN_SUGGESTION_CAP (200): this detector runs once a day, per org, off
# a population that already passed the M3b outage guard, so a well-behaved
# org should rarely approach this — the PRD's "a small number of
# well-evidenced pending suggestions" framing is the operating target, not
# an aspiration. Promote to per-org config only if operators demonstrate a
# real need.
PER_RUN_SUGGESTION_CAP = 10

# Mirrors AutomationRule.mode / the shipped *_classifier_mode columns: this
# is a three-state off|shadow|active gate for WRITES into the churn-
# suggestion review queue, not the classifier off|shadow|auto triple. Any
# value outside this set (including NULL / no OrgAIConfig row at all) is
# treated as 'off' — defence in depth.
_VALID_MODES = {"off", "shadow", "active"}

# A customer whose current usage_trend_state is this value has not been
# classified into a real trend yet (insufficient warm-up data) and is
# deliberately excluded from the M3b "trend-eligible" population — mirrors
# how usage_trend_severity.py's TREND_SEVERITY omits this state entirely,
# because it is an absence of evidence, not evidence of anything. Neither
# inflating nor deflating the population denominator with these rows.
_NOT_TREND_ELIGIBLE_STATE = "insufficient_history"


def _resolve_mode_and_sustain_days(org_id: int, db) -> Tuple[str, int]:
    """Read usage_churn_labels_mode + sustain_days from the org's OrgAIConfig.

    No OrgAIConfig row, a NULL mode, or an unrecognized mode string all
    resolve to 'off'. `sustain_days` defaults to DEFAULT_SUSTAIN_DAYS when
    `usage_churn_label_config` is NULL, not a dict, or the key is
    absent/falsy.
    """
    from src.models import OrgAIConfig

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    if config is None:
        return "off", DEFAULT_SUSTAIN_DAYS

    mode = config.usage_churn_labels_mode
    if mode not in _VALID_MODES:
        mode = "off"

    sustain_days = DEFAULT_SUSTAIN_DAYS
    label_config = config.usage_churn_label_config
    if isinstance(label_config, dict):
        configured = label_config.get("sustain_days")
        if configured:
            sustain_days = configured

    return mode, sustain_days


def _load_customers(
    org_id: int, db
) -> List[Tuple[str, Optional[datetime], Optional[str], Optional[float], Optional[int]]]:
    """Every (customer_email, last_active_at, usage_trend_state,
    usage_trend_pct, active_days_14d) row for the org's customer_usage
    rollups.

    The trend_pct/active_days_14d columns are read here purely to feed
    `build_evidence` for qualifying customers (Phase 4) — still exactly the
    one batched SELECT this function has always issued, no new query.
    """
    from src.models import CustomerUsage

    rows = (
        db.query(
            CustomerUsage.customer_email,
            CustomerUsage.last_active_at,
            CustomerUsage.usage_trend_state,
            CustomerUsage.usage_trend_pct,
            CustomerUsage.active_days_14d,
        )
        .filter(CustomerUsage.organization_id == org_id)
        .all()
    )
    return [
        (email, last_active_at, trend_state, trend_pct, active_days_14d)
        for email, last_active_at, trend_state, trend_pct, active_days_14d in rows
    ]


def _existing_suggestion_row(db, org_id: int, external_opportunity_id: str):
    """Natural-key pre-check.

    Copied (NOT imported) from `churn_suggestion_harvester._existing_suggestion_row`
    (:48-59) per the plan's "reuse by copying" directive — this module must
    never import from the CRM harvest path. `provider` is hardcoded to
    `PROVIDER` (this module only ever writes one provider's rows).
    """
    from src.models import ChurnLabelSuggestion

    return (
        db.query(ChurnLabelSuggestion)
        .filter_by(
            organization_id=org_id,
            provider=PROVIDER,
            external_opportunity_id=external_opportunity_id,
        )
        .first()
    )


def _has_active_churn_event(db, org_id: int, customer_email: str) -> bool:
    """Copied (NOT imported) from
    `churn_suggestion_harvester._has_active_churn_event` (:62-79): org +
    email + recovered_at IS NULL.
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


def _load_streak_window_history(
    org_id: int,
    db,
    customer_emails: List[str],
    today: date,
    sustain_days: int,
) -> Dict[str, List[Tuple[date, str, Optional[int]]]]:
    """One batched query resolving the streak window for EVERY customer in
    `customer_emails` — mirrors `_load_trend_baselines`
    (usage_metrics.py:279-338): a single SELECT scoped to the org and a
    calendar-date window, grouped in Python by customer_email. Never query
    per customer. Uses the composite index
    `ix_customer_usage_history_lookback (organization_id, customer_email,
    snapshot_date)`.

    The window is CALENDAR days — `[today - (sustain_days - 1), today]` —
    not "the last N existing rows". This distinction matters: if the query
    instead pulled the N most-recent existing rows (ORDER BY snapshot_date
    DESC LIMIT N per customer), a gap near today (e.g. from a worker outage)
    would cause it to silently reach past the gap into an older, already-
    ended streak and hand `qualifying_streak` a run that LOOKS complete but
    is stale. Calendar-window filtering instead returns fewer than
    `sustain_days` rows whenever there's a gap in that exact window, which
    `qualifying_streak`'s own length check correctly reads as "does not
    qualify" — conservative under our own downtime, by construction.

    Each tuple also carries `active_days_14d` (Phase 4): `qualifying_streak`
    only ever looks at the (date, trend_state) pair, but a qualifying
    customer's window rows are reused as-is to build `evidence.
    snapshot_series` and the `baseline_active_days_14d` value — still no
    second query.
    """
    from src.models import CustomerUsageHistory

    if not customer_emails:
        return {}

    earliest_date = today - timedelta(days=sustain_days - 1)

    rows = (
        db.query(
            CustomerUsageHistory.customer_email,
            CustomerUsageHistory.snapshot_date,
            CustomerUsageHistory.usage_trend_state,
            CustomerUsageHistory.active_days_14d,
        )
        .filter(
            CustomerUsageHistory.organization_id == org_id,
            CustomerUsageHistory.customer_email.in_(customer_emails),
            CustomerUsageHistory.snapshot_date >= earliest_date,
            CustomerUsageHistory.snapshot_date <= today,
        )
        .all()
    )

    history: Dict[str, List[Tuple[date, str, Optional[int]]]] = defaultdict(list)
    for email, snapshot_date, trend_state, active_days_14d in rows:
        history[email].append((snapshot_date, trend_state, active_days_14d))

    return history


def detect_usage_decline_labels(
    org_id: int,
    db,
    *,
    today: Optional[date] = None,
) -> dict:
    """Evaluate one org's customers for sustained usage-decline churn-label
    candidates.

    Phase 1: mode gate. Phase 2: batched history load. Phase 3: the M3b
    population-level outage guard, enforced BEFORE any write. Phase 4:
    'active' mode writes a pending `ChurnLabelSuggestion` per qualifying,
    non-denied customer; 'shadow' mode still writes zero rows.

    Args:
        org_id: organization to evaluate.
        db: SQLAlchemy session. Caller owns the transaction — this function
            never calls `db.commit()` (it uses `db.begin_nested()` for the
            per-row savepoint, matching `churn_suggestion_harvester.py`'s
            race backstop, but leaves the outer commit to the caller).
        today: override for the "as of" calendar date (tests only); defaults
            to `datetime.utcnow().date()`.

    Returns:
        dict with at least a `status` key: `skipped` (mode='off', no
        customer/history query performed at all), `suppressed` (M3b outage
        guard tripped — see `reason`, `qualifying`, `eligible`), `shadow`
        (evaluated, zero writes), or `evaluated` (mode='active' — see
        `written`/`skipped_existing`/`skipped_no_last_active`/
        `dropped_by_cap`).
    """
    mode, sustain_days = _resolve_mode_and_sustain_days(org_id, db)

    if mode == "off":
        logger.info(
            "usage_decline_label_detector: org=%s mode=off — skipping, "
            "no history query performed",
            org_id,
        )
        return {
            "status": "skipped",
            "reason": "mode_off",
            "org_id": org_id,
            "mode": mode,
        }

    if today is None:
        today = datetime.utcnow().date()

    customers = _load_customers(org_id, db)
    customer_emails = [email for email, _, _, _, _ in customers]

    history_by_email = _load_streak_window_history(
        org_id, db, customer_emails, today, sustain_days
    )

    eligible = 0
    qualifying: List[dict] = []
    for email, last_active_at, trend_state, trend_pct, current_active_days_14d in customers:
        if trend_state is None or trend_state == _NOT_TREND_ELIGIBLE_STATE:
            # Not trend-eligible: excluded from the M3b denominator
            # entirely — never counted toward `eligible` or `qualifying`.
            continue
        eligible += 1

        window_rows = history_by_email.get(email, [])
        states = [(snap_date, state) for snap_date, state, _ in window_rows]
        streak_start = qualifying_streak(states, sustain_days)
        if streak_start is not None:
            qualifying.append({
                "email": email,
                "last_active_at": last_active_at,
                "trend_state": trend_state,
                "trend_pct": trend_pct,
                "current_active_days_14d": current_active_days_14d,
                "streak_start": streak_start,
                "window_rows": window_rows,
            })

    qualifying_count = len(qualifying)

    if outage_suspected(qualifying_count, eligible):
        # House rule: no silent caps/suppressions — this must be LOUD.
        logger.warning(
            "usage_decline_label_detector: possible usage-instrumentation "
            "outage — org=%s qualifying=%s of eligible=%s trend-eligible "
            "customers declined simultaneously (mode=%s); suppressing the "
            "entire run for this org, writing nothing",
            org_id, qualifying_count, eligible, mode,
        )
        return {
            "status": "suppressed",
            "reason": "outage_suspected",
            "org_id": org_id,
            "mode": mode,
            "qualifying": qualifying_count,
            "eligible": eligible,
        }

    if mode == "shadow":
        logger.info(
            "usage_decline_label_detector: org=%s mode=shadow would_suggest=%s "
            "eligible=%s (no ChurnLabelSuggestion rows written)",
            org_id, qualifying_count, eligible,
        )
        return {
            "status": "shadow",
            "org_id": org_id,
            "mode": mode,
            "would_suggest": qualifying_count,
            "eligible": eligible,
        }

    # mode == "active": write a pending ChurnLabelSuggestion for every
    # qualifying customer that isn't denied — natural-key idempotent,
    # capped, never committed here (caller owns the transaction).
    from src.models import ChurnLabelSuggestion

    written = 0
    skipped_existing = 0
    skipped_no_last_active = 0
    dropped_by_cap = 0

    # Deterministic order (by email) so the cap always drops the same
    # customers given the same input, rather than depending on incidental
    # query/dict ordering.
    for candidate in sorted(qualifying, key=lambda c: c["email"]):
        email = candidate["email"]
        last_active_at = candidate["last_active_at"]
        streak_start = candidate["streak_start"]

        if last_active_at is None:
            # Denial: never substitute a fallback date for
            # suggested_churned_at.
            skipped_no_last_active += 1
            continue

        external_opportunity_id = suggestion_key(email, streak_start)

        if _existing_suggestion_row(db, org_id, external_opportunity_id):
            skipped_existing += 1
            continue

        if _has_active_churn_event(db, org_id, email):
            skipped_existing += 1
            continue

        if written >= PER_RUN_SUGGESTION_CAP:
            dropped_by_cap += 1
            continue

        sorted_window = sorted(candidate["window_rows"], key=lambda row: row[0])
        baseline_active_days_14d = sorted_window[0][2] if sorted_window else None
        snapshot_series = [(snap_date, active_days) for snap_date, _, active_days in sorted_window]

        evidence = build_evidence(
            trend_state=candidate["trend_state"],
            trend_pct=candidate["trend_pct"],
            baseline_active_days_14d=baseline_active_days_14d,
            current_active_days_14d=candidate["current_active_days_14d"],
            streak_start_date=streak_start,
            as_of_date=today,
            last_active_at=last_active_at,
            snapshot_series=snapshot_series,
        )

        try:
            with db.begin_nested():
                row = ChurnLabelSuggestion(
                    organization_id=org_id,
                    customer_email=email,
                    provider=PROVIDER,
                    external_opportunity_id=external_opportunity_id,
                    suggested_churned_at=last_active_at,
                    evidence=evidence,
                    status="pending",
                )
                db.add(row)
                db.flush()
            written += 1
        except IntegrityError:
            # Race: another process inserted the same
            # (org, provider, external_opportunity_id) between our
            # pre-check and this flush. The DB UNIQUE constraint is the
            # real guarantee; the pre-check is just the fast path.
            skipped_existing += 1

    if dropped_by_cap:
        # House rule: no silent caps.
        logger.warning(
            "usage_decline_label_detector: per-run cap reached org=%s "
            "cap=%s dropped_by_cap=%s",
            org_id, PER_RUN_SUGGESTION_CAP, dropped_by_cap,
        )

    logger.info(
        "usage_decline_label_detector: org=%s mode=active written=%s "
        "skipped_existing=%s skipped_no_last_active=%s dropped_by_cap=%s "
        "qualifying=%s eligible=%s",
        org_id, written, skipped_existing, skipped_no_last_active,
        dropped_by_cap, qualifying_count, eligible,
    )
    return {
        "status": "evaluated",
        "org_id": org_id,
        "mode": mode,
        "qualifying": qualifying_count,
        "eligible": eligible,
        "written": written,
        "skipped_existing": skipped_existing,
        "skipped_no_last_active": skipped_no_last_active,
        "dropped_by_cap": dropped_by_cap,
    }
