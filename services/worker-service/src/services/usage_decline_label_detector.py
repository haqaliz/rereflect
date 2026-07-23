"""
Usage-decline churn-label detector (worker-detector aspect).

Wires the pure `usage_decline_labels_core` functions to the worker's real
CustomerUsage / CustomerUsageHistory / OrgAIConfig rows.

**Placement (documented, NOT implemented here — that is Phase 5):** this
module's `detect_usage_decline_labels` is meant to eventually be invoked from
`recompute_usage_scores` STRICTLY AFTER the daily snapshot commit
(`usage_metrics.py:693-694`), never at the M3.2c post-commit drain seam
(`:667-681`) — the spec's original placement note was wrong; see
`docs/planning/usage-decline-churn-labels/worker-detector/plan_20260723.md`
section 1. Today's snapshot row does not exist until that final commit, so a
detector run before it would read history missing the current day.

This file currently implements only Phase 1 of that plan: the detector
skeleton + the off/shadow/active mode gate. `active` mode computes and logs
exactly like `shadow` for now — the write path (Phase 4) does not exist yet.

Hard fences (never touched by this module): churn_risk_component,
churn_probability, churn_probability_low/high, calibration_model_id,
time_to_churn_bucket, classify_usage_trend, select_nearest_in_band_snapshot,
apply_trend_penalty, churn_suggestion_harvester.py, churn_harvest_core.py.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple

from src.services.usage_decline_labels_core import qualifying_streak

logger = logging.getLogger(__name__)

# usage_churn_label_config default when NULL or the key is absent/falsy
# (PRD M2).
DEFAULT_SUSTAIN_DAYS = 7

# Mirrors AutomationRule.mode / the shipped *_classifier_mode columns: this
# is a three-state off|shadow|active gate for WRITES into the churn-
# suggestion review queue, not the classifier off|shadow|auto triple. Any
# value outside this set (including NULL / no OrgAIConfig row at all) is
# treated as 'off' — defence in depth.
_VALID_MODES = {"off", "shadow", "active"}


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
) -> List[Tuple[str, Optional[datetime], Optional[str]]]:
    """Every (customer_email, last_active_at, usage_trend_state) row for the
    org's customer_usage rollups.
    """
    from src.models import CustomerUsage

    rows = (
        db.query(
            CustomerUsage.customer_email,
            CustomerUsage.last_active_at,
            CustomerUsage.usage_trend_state,
        )
        .filter(CustomerUsage.organization_id == org_id)
        .all()
    )
    return [(email, last_active_at, trend_state) for email, last_active_at, trend_state in rows]


def _load_history_for_customer(
    org_id: int, db, email: str, today: date, sustain_days: int
) -> List[Tuple[date, str]]:
    """Phase 1 placeholder: one query per customer. Phase 2 replaces this
    with a single org-scoped batched query — see that phase's docstring for
    why "batched" matters at customer-count scale.
    """
    from datetime import timedelta

    from src.models import CustomerUsageHistory

    earliest_date = today - timedelta(days=sustain_days - 1)

    rows = (
        db.query(CustomerUsageHistory.snapshot_date, CustomerUsageHistory.usage_trend_state)
        .filter(
            CustomerUsageHistory.organization_id == org_id,
            CustomerUsageHistory.customer_email == email,
            CustomerUsageHistory.snapshot_date >= earliest_date,
            CustomerUsageHistory.snapshot_date <= today,
        )
        .all()
    )
    return [(snapshot_date, trend_state) for snapshot_date, trend_state in rows]


def detect_usage_decline_labels(
    org_id: int,
    db,
    *,
    today: Optional[date] = None,
) -> dict:
    """Evaluate one org's customers for sustained usage-decline churn-label
    candidates.

    Phase 1 only: mode gate + a working (not yet batched) evaluation loop.
    No write path exists yet — 'active' mode currently only computes and
    logs the same counts as 'shadow'; both write zero `ChurnLabelSuggestion`
    rows.

    Args:
        org_id: organization to evaluate.
        db: SQLAlchemy session. Caller owns the transaction — this function
            never commits (there is nothing to commit yet in Phase 1).
        today: override for the "as of" calendar date (tests only); defaults
            to `datetime.utcnow().date()`.

    Returns:
        dict with at least a `status` key: `skipped` (mode='off', no
        customer/history query performed at all), `shadow`, or `evaluated`
        (mode='active' — no writes yet).
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

    qualifying: List[Tuple[str, date, Optional[datetime]]] = []
    for email, last_active_at, _trend_state in customers:
        states = _load_history_for_customer(org_id, db, email, today, sustain_days)
        streak_start = qualifying_streak(states, sustain_days)
        if streak_start is not None:
            qualifying.append((email, streak_start, last_active_at))

    qualifying_count = len(qualifying)

    if mode == "shadow":
        logger.info(
            "usage_decline_label_detector: org=%s mode=shadow would_suggest=%s "
            "(no ChurnLabelSuggestion rows written)",
            org_id, qualifying_count,
        )
        return {
            "status": "shadow",
            "org_id": org_id,
            "mode": mode,
            "would_suggest": qualifying_count,
        }

    # mode == "active": Phase 4 (out of scope here) will write
    # ChurnLabelSuggestion rows for `qualifying`. Deliberately writes nothing
    # yet — human checkpoint required after Phase 3, before any write path
    # exists (plan section 7).
    logger.info(
        "usage_decline_label_detector: org=%s mode=active qualifying=%s "
        "(write path not yet implemented — Phase 4)",
        org_id, qualifying_count,
    )
    return {
        "status": "evaluated",
        "org_id": org_id,
        "mode": mode,
        "qualifying": qualifying_count,
    }
