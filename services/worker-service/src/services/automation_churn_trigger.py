"""
automation_churn_trigger — focused `churn_probability_threshold` evaluator
for the worker's probability-update seam (Task 4, churn-triggered-playbooks).

Why this exists (read before touching)
---------------------------------------
`churn_probability` is recomputed in the WORKER
(`src.services.probability_updater.update()`), which — unlike the backend
health-score path — does NOT invoke backend-api's `AutomationEngine`
(the worker cannot import backend-api; see `src.clients.asana` for the same
constraint documented elsewhere). This module is a SMALL, ISOLATED mirror of
just the `churn_probability_threshold` trigger + `run_playbook` action slice
of `services/backend-api/src/services/automation_engine.py`.

It deliberately does NOT mirror the whole engine. `src.tasks.analysis` has a
pre-existing dead import (`from src.services.automation_engine import
AutomationEngine`, wrapped in try/except) that has silently never fired the
`feedback_category_match` / `sentiment_pattern` triggers from the worker —
that is a separate, out-of-scope bug and must not be "fixed" by mirroring
the full engine here (doing so would silently activate those triggers, an
unintended behaviour change).

Cooldown semantics are IDENTICAL to the backend engine so that a cooldown
set by either process is honoured by both: Redis DB 1, key
`automation_cooldown:{rule_id}:{customer_email}`, TTL `cooldown_hours * 3600`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models import ChurnPlaybook, ChurnPlaybookExecution
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule
from src.tasks.churn_playbooks import run_playbook

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Redis cooldown client — same DB (1) + key scheme as backend-api's
# AutomationEngine._get_redis / COOLDOWN_KEY_PREFIX.
# ---------------------------------------------------------------------------

COOLDOWN_KEY_PREFIX = "automation_cooldown"

_redis_client = None


def _get_redis():
    """Return a shared Redis client (db=1), or None if Redis is unavailable.

    Mirrors backend-api's `AutomationEngine._get_redis` behaviour: on
    connection failure, cooldowns are simply disabled (rules always fire) —
    never raises.
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
                "automation_churn_trigger: Redis unavailable — cooldowns disabled: %s",
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
        logger.warning("automation_churn_trigger: cooldown check failed: %s", exc)
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
        logger.warning("automation_churn_trigger: failed to set cooldown: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_churn_probability_triggers(
    org_id: int, customer_email: str, probability: float, db: Session
) -> None:
    """
    Evaluate all shadow/active `churn_probability_threshold` rules for
    *org_id* against *probability*, firing `run_playbook` actions for
    breached, non-cooled-down rules.

    Safe to call unconditionally from `probability_updater.update()` — this
    function never raises; per-rule failures are caught and logged so one
    bad rule can't block evaluation of the others (or break the caller).
    """
    try:
        rules: List[AutomationRule] = (
            db.query(AutomationRule)
            .filter(
                AutomationRule.organization_id == org_id,
                AutomationRule.trigger_type == "churn_probability_threshold",
                AutomationRule.mode.in_(["shadow", "active"]),
            )
            .all()
        )
    except Exception as exc:
        logger.error(
            "automation_churn_trigger: failed to load rules for org %s: %s",
            org_id, exc,
        )
        return

    for rule in rules:
        try:
            _evaluate_rule(rule, org_id, customer_email, probability, db)
        except Exception as exc:
            logger.error(
                "automation_churn_trigger: unhandled error evaluating rule %s: %s",
                rule.id, exc,
            )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _evaluate_rule(
    rule: AutomationRule,
    org_id: int,
    customer_email: str,
    probability: float,
    db: Session,
) -> None:
    """Evaluate + (maybe) fire a single rule. Mirrors AutomationEngine._evaluate_rule."""
    cfg = rule.trigger_config or {}
    threshold = float(cfg.get("threshold", 0.7))
    if float(probability) < threshold:
        return

    if _check_cooldown(rule.id, customer_email):
        logger.debug(
            "automation_churn_trigger: rule %s in cooldown for customer %s — skipping",
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
        trigger_snapshot={"churn_probability": probability},
        actions_executed=action_results,
        status=status,
        executed_at=datetime.utcnow(),
    )
    db.add(execution)

    rule.execution_count = (rule.execution_count or 0) + 1
    rule.last_executed_at = datetime.utcnow()

    _set_cooldown(rule.id, customer_email, rule.cooldown_hours)

    db.commit()


def _execute_run_playbook_actions(
    rule: AutomationRule, org_id: int, customer_email: str, db: Session
) -> List[Dict[str, Any]]:
    """
    Execute only `run_playbook` actions from *rule.actions*.

    Non-`run_playbook` action types (`auto_assign`, `change_status`,
    `send_notification`, `draft_response`) are ignored here — the worker
    seam only auto-runs churn playbooks; those other actions remain
    backend-only (fired via the backend health-score path, which does use
    the full AutomationEngine).
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
            triggered_by="auto_probability",
            triggered_by_user_id=None,
            status="queued",
        )
        db.add(exec_row)
        db.flush()

        try:
            run_playbook.delay(exec_row.id)
        except Exception as exc:
            logger.warning(
                "automation_churn_trigger: failed to enqueue run_playbook for execution %s: %s",
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
