"""
automation_usage_trend_trigger — focused `usage_trend` evaluator for the
worker's daily usage-recompute seam (worker-trend-evaluator aspect,
usage-trend-automation-trigger PRD, M1/M5).

Why this exists (read before touching)
---------------------------------------
`usage_trend_state` is (re)classified in the WORKER's daily
`recompute_usage_scores` task (`src.tasks.usage_metrics`), which — like
`churn_probability` in `probability_updater.py` — does NOT invoke
backend-api's `AutomationEngine` (the worker cannot import backend-api).
This module is a SMALL, ISOLATED mirror of just the `usage_trend` trigger +
`run_playbook` action slice of
`services/backend-api/src/services/automation_engine.py`, modeled directly
on the sibling `src.services.automation_churn_trigger` module written for
the `churn_probability_threshold` trigger.

It deliberately does NOT mirror the whole engine, and does NOT grow beyond
`run_playbook` — same warning as `automation_churn_trigger.py`: doing so
would silently activate trigger types / action types that are meant to
remain backend-only.

Edge-triggered semantics (PRD M2): this evaluator fires ONLY on a STRICTLY
WORSENING transition (`stable < declining < sharp_decline`), determined by
`src.services.usage_trend_severity.is_worsening_transition` — the
worker-service DUPLICATE of the backend-api helper of the same name (see
that module's header). `insufficient_history` has no rank; any transition
touching it, in either direction, never fires — this is the warm-up
baseline-seed guard (AC2). A customer who stays in the same state between
two runs produces no transition and does not re-fire (AC3) — this is what
makes activation-time cooldown seeding unnecessary for this trigger
(unlike `churn_probability_threshold`, which is level-based).

Cooldown semantics are IDENTICAL to the backend engine AND to
`automation_churn_trigger.py` so that a cooldown set by any of the three
processes is honoured by all: Redis DB 1, key
`automation_cooldown:{rule_id}:{customer_email}`, TTL `cooldown_hours * 3600`.

`triggered_by` on the resulting `ChurnPlaybookExecution` is the distinct
string `"auto_usage_trend"` (never `"auto_probability"`, which is
M4.1.5's churn-probability value) — see the aspect spec for why this must
be exact.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models import ChurnPlaybook, ChurnPlaybookExecution
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule
from src.services.usage_trend_severity import is_worsening_transition
from src.tasks.churn_playbooks import run_playbook

logger = logging.getLogger(__name__)

# `ChurnPlaybookExecution.triggered_by` value for auto-runs fired by this
# evaluator — distinct from "auto_probability" (M4.1.5). Must stay exactly
# this string: the timeline's `_fetch_playbook_runs` filter is widened to
# match it (see the aspect spec's "triggered_by value" section).
TRIGGERED_BY = "auto_usage_trend"


# ---------------------------------------------------------------------------
# Redis cooldown client — same DB (1) + key scheme as backend-api's
# AutomationEngine._get_redis / COOLDOWN_KEY_PREFIX, and as
# automation_churn_trigger.py, so cooldowns are shared across all three.
# ---------------------------------------------------------------------------

COOLDOWN_KEY_PREFIX = "automation_cooldown"

_redis_client = None


def _get_redis():
    """Return a shared Redis client (db=1), or None if Redis is unavailable.

    Mirrors backend-api's `AutomationEngine._get_redis` /
    `automation_churn_trigger._get_redis` behaviour: on connection failure,
    cooldowns are simply disabled (rules always fire) — never raises.
    """
    global _redis_client
    if _redis_client is None:
        try:
            import redis

            from src.config import get_redis_url

            _redis_client = redis.from_url(
                get_redis_url(1),
                decode_responses=True,
                socket_connect_timeout=2,
            )
            _redis_client.ping()
        except Exception as exc:
            logger.warning(
                "automation_usage_trend_trigger: Redis unavailable — cooldowns disabled: %s",
                exc,
            )
            _redis_client = None
    return _redis_client


def _check_cooldown(rule_id: int, customer_email: str) -> bool:
    """Return True if this rule/customer pair is still in cooldown (skip it)."""
    r = _get_redis()
    if r is None:
        return False  # Redis unavailable → always allow (mirrors engine behaviour)
    key = f"{COOLDOWN_KEY_PREFIX}:{rule_id}:{customer_email}"
    try:
        return bool(r.exists(key))
    except Exception as exc:
        logger.warning("automation_usage_trend_trigger: cooldown check failed: %s", exc)
        return False


def _set_cooldown(rule_id: int, customer_email: str, hours: int) -> None:
    """Set the Redis cooldown key with TTL = hours * 3600 seconds."""
    r = _get_redis()
    if r is None:
        return
    key = f"{COOLDOWN_KEY_PREFIX}:{rule_id}:{customer_email}"
    try:
        r.setex(key, int(hours or 0) * 3600, "1")
    except Exception as exc:
        logger.warning("automation_usage_trend_trigger: failed to set cooldown: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_usage_trend_triggers(
    org_id: int,
    customer_email: str,
    old_trend_state: Optional[str],
    new_trend_state: Optional[str],
    db: Session,
) -> None:
    """
    Evaluate all shadow/active `usage_trend` rules for *org_id* against the
    *old_trend_state* -> *new_trend_state* transition, firing `run_playbook`
    actions for matching, non-cooled-down rules.

    MUST be called only AFTER the caller has committed *new_trend_state* —
    this function does not itself validate that (see
    `src.tasks.usage_metrics.recompute_usage_scores`, which drains
    accumulated transitions through this function strictly after its
    `db.commit()`, never inside the scan loop).

    Safe to call unconditionally — this function never raises; per-rule
    failures are caught and logged so one bad rule can't block evaluation
    of the others (or break the caller, e.g. the daily recompute task).
    """
    try:
        rules: List[AutomationRule] = (
            db.query(AutomationRule)
            .filter(
                AutomationRule.organization_id == org_id,
                AutomationRule.trigger_type == "usage_trend",
                AutomationRule.mode.in_(["shadow", "active"]),
            )
            .all()
        )
    except Exception as exc:
        logger.error(
            "automation_usage_trend_trigger: failed to load rules for org %s: %s",
            org_id, exc,
        )
        return

    for rule in rules:
        try:
            _evaluate_rule(rule, org_id, customer_email, old_trend_state, new_trend_state, db)
        except Exception as exc:
            logger.error(
                "automation_usage_trend_trigger: unhandled error evaluating rule %s: %s",
                rule.id, exc,
            )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _evaluate_rule(
    rule: AutomationRule,
    org_id: int,
    customer_email: str,
    old_trend_state: Optional[str],
    new_trend_state: Optional[str],
    db: Session,
) -> None:
    """Evaluate + (maybe) fire a single rule.

    Mirrors AutomationEngine._trigger_usage_trend + _evaluate_rule: fire
    only when *new_trend_state* is one of the rule's configured target
    states AND the transition is strictly worsening (never on a same-state
    repeat, a recovery, or anything touching `insufficient_history`).
    """
    cfg = rule.trigger_config or {}
    states = cfg.get("states") or []
    if new_trend_state not in states:
        return
    if not is_worsening_transition(old_trend_state, new_trend_state):
        return

    if _check_cooldown(rule.id, customer_email):
        logger.debug(
            "automation_usage_trend_trigger: rule %s in cooldown for customer %s — skipping",
            rule.id, customer_email,
        )
        return

    if rule.mode == "shadow":
        action_results: List[Dict[str, Any]] = []
        status = "shadow"
    else:
        action_results = _execute_run_playbook_actions(rule, org_id, customer_email, db)
        errors = [r for r in action_results if r.get("error")]
        if not errors:
            status = "success"
        elif len(errors) < len(action_results):
            status = "partial_failure"
        else:
            status = "failed"

    execution = AutomationExecution(
        rule_id=rule.id,
        organization_id=rule.organization_id,
        feedback_id=None,
        customer_email=customer_email or None,
        trigger_snapshot={
            "old_trend_state": old_trend_state,
            "new_trend_state": new_trend_state,
        },
        actions_executed=action_results,
        status=status,
        executed_at=datetime.utcnow(),
    )
    db.add(execution)

    rule.execution_count = (rule.execution_count or 0) + 1
    rule.last_executed_at = datetime.utcnow()

    # Shadow mode still consumes the cooldown (spec AC5) — a would-have-run
    # log entry every single run for an already-declining customer would be
    # noise, not signal.
    _set_cooldown(rule.id, customer_email, rule.cooldown_hours)

    db.commit()


def _execute_run_playbook_actions(
    rule: AutomationRule, org_id: int, customer_email: str, db: Session
) -> List[Dict[str, Any]]:
    """
    Execute only `run_playbook` actions from *rule.actions*.

    Non-`run_playbook` action types are ignored here — same deliberately
    narrow scope as `automation_churn_trigger._execute_run_playbook_actions`
    (the worker seam only auto-runs churn playbooks).
    """
    results: List[Dict[str, Any]] = []
    for action in (rule.actions or []):
        if not isinstance(action, dict) or action.get("type") != "run_playbook":
            continue

        config: dict = action.get("config", {}) or {}
        playbook_id = config.get("playbook_id")
        if not playbook_id:
            results.append(
                {"type": "run_playbook", "result": None, "error": "missing playbook_id"}
            )
            continue

        playbook: Optional[ChurnPlaybook] = (
            db.query(ChurnPlaybook)
            .filter(
                ChurnPlaybook.id == playbook_id,
                ChurnPlaybook.is_active.is_(True),
                (ChurnPlaybook.organization_id == org_id)
                | (ChurnPlaybook.organization_id.is_(None)),
            )
            .first()
        )
        if playbook is None:
            results.append(
                {
                    "type": "run_playbook",
                    "result": None,
                    "error": "playbook not found / inactive / wrong org",
                }
            )
            continue

        exec_row = ChurnPlaybookExecution(
            playbook_id=playbook_id,
            organization_id=org_id,
            customer_email=customer_email,
            triggered_by=TRIGGERED_BY,
            triggered_by_user_id=None,
            status="queued",
        )
        db.add(exec_row)
        db.flush()

        try:
            run_playbook.delay(exec_row.id)
        except Exception as exc:
            logger.warning(
                "automation_usage_trend_trigger: failed to enqueue run_playbook "
                "for execution %s: %s",
                exec_row.id, exc,
            )

        results.append(
            {
                "type": "run_playbook",
                "result": {"execution_id": exec_row.id, "playbook_id": playbook_id},
                "error": None,
            }
        )

    return results
