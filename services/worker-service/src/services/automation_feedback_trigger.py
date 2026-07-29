"""
automation_feedback_trigger — worker-side mirror of the `feedback_category_match`,
`sentiment_pattern`, and (added for batch-sentiment-trigger, Track B)
`batch_sentiment_threshold` triggers (worker-trigger-mirror, aspect 2).

Why this exists (read before touching)
---------------------------------------
`services/worker-service/src/tasks/analysis.py` had a pre-existing dead
import: `from src.services.automation_engine import AutomationEngine`, wrapped
in a bare `except Exception` that just logged a warning. That module does
NOT exist in worker-service (the worker cannot import backend-api — see
`src.services.automation_churn_trigger` for the same constraint documented
elsewhere), and the Docker image never receives backend-api's package. The
`ImportError` fired on EVERY analysis and was swallowed, so
`feedback_category_match` and `sentiment_pattern` have NEVER executed in any
deployment.

This module is a full mirror of just those two triggers, matching the
structural precedent of `src.services.automation_churn_trigger`:
module-level docstring, `_get_redis()` returning `None` on failure (cooldowns
disabled, never raises), its own direct `AutomationExecution` writes.

It is the SOURCE OF TRUTH counterpart to
`services/backend-api/src/services/automation_engine.py`
(`AutomationEngine._trigger_feedback_category`,
`AutomationEngine._trigger_sentiment_pattern`, and
`AutomationEngine._execute_actions`), ported verbatim here. **Any change to
trigger or action semantics must be made in BOTH places** — the worker
cannot import the backend engine, so nothing keeps these in sync but
discipline and this comment (see automation_engine.py for the reciprocal
pointer).

Unlike `automation_churn_trigger` (which only implements `run_playbook`),
this mirror implements the other four action types
(`auto_assign`, `change_status`, `send_notification`, `draft_response`) —
`run_playbook` is explicitly OUT of scope here and, like any other
unimplemented action type, must record a loud `error` in `actions_executed`
rather than being silently skipped (that silent-skip class of bug is exactly
what this module exists to fix).

Cooldown semantics are IDENTICAL to the backend engine so that a cooldown
set by either process is honoured by both: Redis DB 1, key
`automation_cooldown:{rule_id}:{customer_email}`, TTL `cooldown_hours * 3600`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.email import _send_with_template
from src.models import FeedbackItem, Integration, Notification, User
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule
from src.tasks.alerts import send_slack_message_webhook

logger = logging.getLogger(__name__)

# Trigger types this mirror is allowed to evaluate. Every other trigger_type
# (health_score_threshold, churn_risk_level_change, churn_probability_threshold,
# usage_trend) remains backend-only / out of scope for this seam.
#
# batch_sentiment_threshold is the odd one out: it is the first ORG-WIDE
# trigger (see docs/planning/batch-sentiment-trigger/trigger-core/spec.md,
# "THE CONTRACT") — every other entry here is evaluated per-customer. Its
# cooldown identity is the sentinel "__org__", not a customer_email; see
# `_evaluate_rule`'s `cooldown_identity` branch and `_trigger_batch_sentiment`
# below.
FEEDBACK_TRIGGER_TYPES = (
    "feedback_category_match",
    "sentiment_pattern",
    "batch_sentiment_threshold",
)

# Channels _execute_notify knows how to deliver. Any other string in a
# rule's `channels` config is recorded as a loud error instead of being
# silently dropped — mirrors backend-api's KNOWN_NOTIFY_CHANNELS.
KNOWN_NOTIFY_CHANNELS = {"dashboard", "email", "slack"}

# Same Resend template used by backend-api's send_alert_email
# (services/backend-api/src/services/email_service.py) — sharing the env var
# name means an operator only has to configure one Resend template for both
# processes' generic "automation triggered" alert email.
TEMPLATE_ALERT_NOTIFICATION = os.getenv("RESEND_TEMPLATE_ALERT_NOTIFICATION")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")


# ---------------------------------------------------------------------------
# Redis cooldown client — same DB (1) + key scheme as backend-api's
# AutomationEngine._get_redis / COOLDOWN_KEY_PREFIX, and as
# automation_churn_trigger._get_redis.
# ---------------------------------------------------------------------------

COOLDOWN_KEY_PREFIX = "automation_cooldown"

_redis_client = None


def _get_redis():
    """Return a shared Redis client (db=1), or None if Redis is unavailable.

    Mirrors backend-api's `AutomationEngine._get_redis` (and
    `automation_churn_trigger._get_redis`) behaviour: on connection failure,
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
                "automation_feedback_trigger: Redis unavailable — cooldowns disabled: %s",
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
        logger.warning("automation_feedback_trigger: cooldown check failed: %s", exc)
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
        logger.warning("automation_feedback_trigger: failed to set cooldown: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_feedback_triggers(
    db: Session, org_id: int, context: Dict[str, Any]
) -> List[Dict]:
    """
    Evaluate all shadow/active `feedback_category_match` and `sentiment_pattern`
    rules for *org_id* against *context*.

    context shape: {"customer_email": str, "feedback_id": int} — same shape
    AutomationEngine.evaluate() is called with for these two event types.

    Returns a list of execution summary dicts, one per rule that fired.
    Safe to call unconditionally after analysis — per-rule failures are
    caught and logged so one bad rule can't block evaluation of the others
    or raise up into the caller.
    """
    try:
        rules: List[AutomationRule] = (
            db.query(AutomationRule)
            .filter(
                AutomationRule.organization_id == org_id,
                AutomationRule.trigger_type.in_(FEEDBACK_TRIGGER_TYPES),
                AutomationRule.mode.in_(["shadow", "active"]),
            )
            .all()
        )
    except Exception as exc:
        logger.error(
            "automation_feedback_trigger: failed to load rules for org %s: %s",
            org_id, exc,
        )
        return []

    results: List[Dict] = []
    for rule in rules:
        try:
            result = _evaluate_rule(rule, context, db)
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.error(
                "automation_feedback_trigger: unhandled error evaluating rule %s: %s",
                rule.id, exc,
            )

    return results


# ---------------------------------------------------------------------------
# Internal — rule evaluation
# ---------------------------------------------------------------------------


# Sentinel cooldown identity for org-wide triggers (currently only
# batch_sentiment_threshold — THE CONTRACT, B3). One rule => one shared
# cooldown key, regardless of which customer's feedback happened to be the
# pivot item. This value must NEVER be written to
# AutomationExecution.customer_email — see `_evaluate_rule` below.
ORG_WIDE_COOLDOWN_IDENTITY = "__org__"

# Trigger types that are evaluated org-wide rather than per-customer. Kept
# as its own set (rather than hardcoding the string inline) so a future
# second org-wide trigger only has to be added here.
ORG_WIDE_TRIGGER_TYPES = ("batch_sentiment_threshold",)


def _evaluate_rule(
    rule: AutomationRule, context: Dict[str, Any], db: Session
) -> Optional[Dict]:
    """Evaluate a single rule. Mirrors AutomationEngine._evaluate_rule."""
    customer_email: str = context.get("customer_email", "")
    feedback_id: Optional[int] = context.get("feedback_id")

    is_org_wide = rule.trigger_type in ORG_WIDE_TRIGGER_TYPES
    cooldown_identity = ORG_WIDE_COOLDOWN_IDENTITY if is_org_wide else customer_email

    # Cooldown is checked BEFORE the (potentially expensive, aggregate-
    # query-driven) trigger evaluation — THE CONTRACT's short-circuit order,
    # step 1. This also fixes the org-wide identity: batch_sentiment_threshold
    # must use ONE key per rule ("__org__"), not one per customer_email.
    if _check_cooldown(rule.id, cooldown_identity):
        logger.debug(
            "automation_feedback_trigger: rule %s in cooldown for %s — skipping",
            rule.id, cooldown_identity,
        )
        return None

    if not _check_trigger(rule, context, db):
        return None

    feedback: Optional[FeedbackItem] = None
    if feedback_id:
        feedback = db.query(FeedbackItem).filter(FeedbackItem.id == feedback_id).first()

    if rule.mode == "shadow":
        action_results: List[Dict] = []
        status = "shadow"
    else:
        action_results = _execute_actions(rule, feedback, context, db)
        errors = [r for r in action_results if r.get("error")]
        if not errors:
            status = "success"
        elif len(errors) < len(action_results):
            status = "partial_failure"
        else:
            status = "failed"

    # Org-wide executions must log customer_email = NULL even though a real
    # customer_email may be present in `context` (it belongs to whichever
    # feedback item happened to be the pivot, not to "the org"). The
    # ORG_WIDE_COOLDOWN_IDENTITY sentinel is kept strictly local to the
    # cooldown key above and must never reach this column — THE CONTRACT, B3.
    execution_customer_email = None if is_org_wide else (customer_email or None)

    execution = AutomationExecution(
        rule_id=rule.id,
        organization_id=rule.organization_id,
        feedback_id=feedback.id if feedback else None,
        customer_email=execution_customer_email,
        trigger_snapshot=context,
        actions_executed=action_results,
        status=status,
        executed_at=datetime.utcnow(),
    )
    db.add(execution)

    rule.execution_count = (rule.execution_count or 0) + 1
    rule.last_executed_at = datetime.utcnow()

    _set_cooldown(rule.id, cooldown_identity, rule.cooldown_hours)

    db.commit()

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "status": status,
        "actions": action_results,
    }


# ---------------------------------------------------------------------------
# Internal — trigger evaluation (ported verbatim from
# AutomationEngine._trigger_feedback_category / _trigger_sentiment_pattern —
# do not re-derive; any deviation from the backend engine is a bug)
# ---------------------------------------------------------------------------


def _check_trigger(rule: AutomationRule, context: Dict[str, Any], db: Session) -> bool:
    """Dispatch to the correct trigger checker based on rule.trigger_type."""
    t = rule.trigger_type
    cfg = rule.trigger_config or {}

    if t == "feedback_category_match":
        return _trigger_feedback_category(cfg, context, db)
    if t == "sentiment_pattern":
        return _trigger_sentiment_pattern(cfg, context, db)
    if t == "batch_sentiment_threshold":
        return _trigger_batch_sentiment(cfg, context, db)

    logger.warning("automation_feedback_trigger: unknown trigger type '%s'", t)
    return False


def _trigger_feedback_category(cfg: dict, context: dict, db: Session) -> bool:
    """Fire when feedback categories intersect with configured categories."""
    configured_categories: List[str] = cfg.get("categories", [])
    if not configured_categories:
        return False

    feedback_id: Optional[int] = context.get("feedback_id")
    if not feedback_id:
        return False

    feedback = db.query(FeedbackItem).filter(FeedbackItem.id == feedback_id).first()
    if not feedback:
        return False

    feedback_categories: List[str] = []
    if feedback.pain_point_category:
        feedback_categories.append(feedback.pain_point_category)
    if feedback.feature_request_category:
        feedback_categories.append(feedback.feature_request_category)
    if feedback.urgent_category:
        feedback_categories.append(feedback.urgent_category)
    if feedback.tags and isinstance(feedback.tags, list):
        feedback_categories.extend(feedback.tags)

    if not set(configured_categories).intersection(set(feedback_categories)):
        return False

    required_urgent = cfg.get("is_urgent")
    if required_urgent is not None and bool(required_urgent) != bool(feedback.is_urgent):
        return False

    return True


def _trigger_sentiment_pattern(cfg: dict, context: dict, db: Session) -> bool:
    """Fire when customer has >= count feedbacks of `sentiment` in last *days* days."""
    required_count: int = cfg.get("count", 3)
    days: int = cfg.get("days", 7)
    sentiment: str = cfg.get("sentiment", "negative")
    customer_email: str = context.get("customer_email", "")

    if not customer_email:
        return False

    cutoff = datetime.utcnow() - timedelta(days=days)

    # Determine org_id from any recent feedback by this customer
    sample = (
        db.query(FeedbackItem.organization_id)
        .filter(FeedbackItem.customer_email == customer_email)
        .first()
    )
    if not sample:
        return False
    org_id = sample.organization_id

    count = (
        db.query(func.count(FeedbackItem.id))
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.customer_email == customer_email,
            FeedbackItem.sentiment_label == sentiment,
            FeedbackItem.created_at >= cutoff,
        )
        .scalar()
        or 0
    )
    return int(count) >= int(required_count)


def _trigger_batch_sentiment(cfg: dict, context: dict, db: Session) -> bool:
    """Fire when the org's feedback in a trailing window crosses a sentiment
    threshold — THE CONTRACT (docs/planning/batch-sentiment-trigger/
    trigger-core/spec.md). The FIRST org-wide trigger in this mirror: it
    reasons about the org's aggregate mix, not a single customer's history.

    Firing rule, evaluated over the org's FeedbackItem rows with
    created_at >= now - window_hours:
        total    = count(all feedback in window)
        matching = count(feedback in window with sentiment_label == cfg["sentiment"])
        if total < min_total:        -> DO NOT FIRE  (sample floor)
        mode == "percentage"         -> fire when matching / total >= threshold
        mode == "count"              -> fire when matching >= threshold

    Short-circuit order (THE CONTRACT, performance/PRD R6). Step 1 (cooldown)
    is checked by the caller, `_evaluate_rule`, strictly BEFORE this function
    is ever invoked (it computes the org-wide "__org__" identity ahead of
    `_check_trigger`). This function owns step 2: skip before running any
    aggregate COUNT unless the pivot feedback item in hand matches
    cfg["sentiment"] — only step 3, the COUNT queries, is expensive.
    """
    sentiment: str = cfg.get("sentiment", "negative")
    feedback_id: Optional[int] = context.get("feedback_id")
    if not feedback_id:
        return False

    feedback = db.query(FeedbackItem).filter(FeedbackItem.id == feedback_id).first()
    if not feedback:
        return False

    # Step 2 — cheap single-row check before any aggregate query.
    if feedback.sentiment_label != sentiment:
        return False

    window_hours: int = cfg.get("window_hours", 24)
    mode: str = cfg.get("mode", "percentage")
    threshold: float = cfg.get("threshold", 0.5)
    min_total: int = cfg.get("min_total", 5)

    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    org_id = feedback.organization_id

    # Step 3 — the aggregate COUNT queries, only reached once steps 1 and 2
    # have both passed.
    total = (
        db.query(func.count(FeedbackItem.id))
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.created_at >= cutoff,
        )
        .scalar()
        or 0
    )

    if total < min_total:
        return False

    matching = (
        db.query(func.count(FeedbackItem.id))
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.created_at >= cutoff,
            FeedbackItem.sentiment_label == sentiment,
        )
        .scalar()
        or 0
    )

    if mode == "count":
        return int(matching) >= threshold
    return (matching / total) >= threshold


# ---------------------------------------------------------------------------
# Internal — action execution (ported from AutomationEngine._execute_actions
# and friends, adapted to worker-local models/senders where the backend
# equivalent isn't importable here)
# ---------------------------------------------------------------------------


def _execute_actions(
    rule: AutomationRule,
    feedback: Optional[FeedbackItem],
    context: Dict[str, Any],
    db: Session,
) -> List[Dict]:
    """Execute all rule actions sequentially. Returns list of {type, result, error}.

    Any action type this mirror does not implement (including `run_playbook`,
    which is out of scope here — the other two worker mirrors own it) is
    recorded with an explicit error, never silently skipped.
    """
    results: List[Dict] = []
    for action in (rule.actions or []):
        if not isinstance(action, dict):
            continue
        action_type: str = action.get("type", "")
        action_config: dict = action.get("config", {}) or {}
        try:
            if action_type == "auto_assign":
                r = _execute_assign(action_config, feedback, db)
            elif action_type == "change_status":
                r = _execute_change_status(action_config, feedback)
            elif action_type == "send_notification":
                r = _execute_notify(action_config, feedback, rule, db)
            elif action_type == "draft_response":
                r = _execute_draft_response(action_config, feedback, db)
            else:
                r = {
                    "type": action_type,
                    "result": None,
                    "error": f"Unsupported action type in worker mirror: {action_type}",
                }
        except Exception as exc:
            logger.error(
                "automation_feedback_trigger: action '%s' failed on rule %s: %s",
                action_type, rule.id, exc,
            )
            r = {"type": action_type, "result": None, "error": str(exc)}
        results.append(r)
    return results


def _round_robin_assign(db: Session, org_id: int) -> Optional[int]:
    """Assign to the org member with the fewest open (new + in_review) items.

    Mirrors backend-api's `src.services.workflow_service.round_robin_assign`
    (not importable from the worker) — same query, worker-local models.
    """
    open_count = (
        db.query(
            FeedbackItem.assigned_to,
            func.count(FeedbackItem.id).label("open_count"),
        )
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.workflow_status.in_(["new", "in_review"]),
            FeedbackItem.assigned_to.isnot(None),
        )
        .group_by(FeedbackItem.assigned_to)
        .subquery()
    )

    member = (
        db.query(User.id, func.coalesce(open_count.c.open_count, 0).label("cnt"))
        .outerjoin(open_count, User.id == open_count.c.assigned_to)
        .filter(User.organization_id == org_id)
        .order_by(func.coalesce(open_count.c.open_count, 0).asc(), User.id.asc())
        .first()
    )
    return member.id if member else None


def _execute_assign(
    config: dict, feedback: Optional[FeedbackItem], db: Session
) -> Dict:
    """
    Assign the feedback item.

    assign_to values:
      "user:{id}"    → assign to specific user
      "role:owner"   → assign to first org owner
      "role:admin"   → assign to first org admin
      "round_robin"  → use round-robin load-balancing
    """
    if feedback is None:
        return {"type": "auto_assign", "result": None, "error": "No feedback object"}

    assign_to: str = config.get("assign_to", "round_robin")
    org_id = feedback.organization_id
    assigned_id: Optional[int] = None

    if assign_to.startswith("user:"):
        try:
            user_id = int(assign_to.split(":")[1])
            user = db.query(User).filter(
                User.id == user_id,
                User.organization_id == org_id,
            ).first()
            if user:
                assigned_id = user.id
        except (ValueError, IndexError):
            pass
    elif assign_to.startswith("role:"):
        role = assign_to.split(":")[1]
        user = (
            db.query(User)
            .filter(User.organization_id == org_id, User.role == role)
            .first()
        )
        if user:
            assigned_id = user.id
    else:
        assigned_id = _round_robin_assign(db, org_id)

    if assigned_id:
        feedback.assigned_to = assigned_id

    return {
        "type": "auto_assign",
        "result": {"assigned_to": assigned_id},
        "error": None,
    }


def _execute_change_status(config: dict, feedback: Optional[FeedbackItem]) -> Dict:
    """Update feedback.workflow_status to config["status"]."""
    if feedback is None:
        return {"type": "change_status", "result": None, "error": "No feedback object"}

    new_status: str = config.get("status", "in_review")
    old_status = feedback.workflow_status
    feedback.workflow_status = new_status

    return {
        "type": "change_status",
        "result": {"old_status": old_status, "new_status": new_status},
        "error": None,
    }


def _send_email_notification(to_email: str, rule_name: str, message: str) -> bool:
    """Send the generic "automation triggered" alert email via Resend.

    Mirrors backend-api's `send_alert_email` (alert_type="automation_trigger")
    using the SAME Resend template env var name
    (`RESEND_TEMPLATE_ALERT_NOTIFICATION`) so operators configure one
    template for both processes. Never raises — callers already wrap this in
    try/except, matching the backend engine's email branch.
    """
    dashboard_url = f"{APP_URL}/dashboard"
    unsubscribe_url = f"{APP_URL}/settings/notifications"
    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_ALERT_NOTIFICATION,
        variables={
            "ALERT_TYPE": "Automation Trigger",
            "ALERT_TITLE": f"Automation: {rule_name}",
            "ALERT_DESCRIPTION": message,
            "DASHBOARD_URL": dashboard_url,
            "UNSUBSCRIBE_URL": unsubscribe_url,
        },
    )


def _execute_notify(
    config: dict,
    feedback: Optional[FeedbackItem],
    rule: AutomationRule,
    db: Session,
) -> Dict:
    """
    Create in-app / email / Slack notifications for the configured recipients.

    recipients: "assignee" | "admins" | "owner" | "user:{id}"
    channels:   any non-empty subset of KNOWN_NOTIFY_CHANNELS =
                {"dashboard", "email", "slack"}.

    "dashboard" and "email" are per-recipient (one Notification / email per
    resolved user id). "slack" is org-wide: it posts once per rule firing to
    every active `Integration` row with type="slack" for the org, regardless
    of how many recipients were resolved — Slack has no per-user identity
    here. Mirrors AutomationEngine._execute_notify exactly.

    CONTRACT DIFFERENCE from the backend: the worker's
    `send_slack_message_webhook` RAISES on failure (backend's returns a
    status dict) — wrapped in try/except here accordingly.

    Any channel string outside KNOWN_NOTIFY_CHANNELS is logged as a warning
    and recorded as a channel error rather than silently dropped. The
    returned "error" is `None` only when every requested channel was
    delivered; otherwise it is a "; "-joined summary of every channel
    failure, so `_evaluate_rule` computes "partial_failure" (or "failed")
    instead of a false "success".
    """
    org_id = rule.organization_id
    recipients: str = config.get("recipients", "admins")
    channels: List[str] = config.get("channels", ["dashboard"])
    message_template: str = config.get(
        "message_template",
        f"Automation '{rule.name}' triggered for feedback #{feedback.id if feedback else '?'}",
    )

    channel_errors: List[str] = []

    # Resolve recipient user IDs
    target_user_ids: List[int] = []

    if recipients == "admins":
        users = (
            db.query(User)
            .filter(User.organization_id == org_id, User.role.in_(["admin", "owner"]))
            .all()
        )
        target_user_ids = [u.id for u in users]
    elif recipients == "owner":
        users = (
            db.query(User)
            .filter(User.organization_id == org_id, User.role == "owner")
            .all()
        )
        target_user_ids = [u.id for u in users]
    elif recipients == "assignee":
        if feedback and feedback.assigned_to:
            target_user_ids = [feedback.assigned_to]
    elif recipients.startswith("user:"):
        try:
            target_user_ids = [int(recipients.split(":")[1])]
        except (ValueError, IndexError):
            pass

    created_count = 0
    for uid in target_user_ids:
        if "dashboard" in channels:
            notification = Notification(
                user_id=uid,
                organization_id=org_id,
                type="automation_trigger",
                title=f"Automation: {rule.name}",
                message=message_template,
                link=f"/feedbacks/{feedback.id}" if feedback else None,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
            db.add(notification)
            created_count += 1

        if "email" in channels:
            try:
                user = db.query(User).filter(User.id == uid).first()
                if user:
                    _send_email_notification(user.email, rule.name, message_template)
            except Exception as exc:
                logger.warning(
                    "automation_feedback_trigger: email notify failed for user %s: %s",
                    uid, exc,
                )

    # Slack is org-wide and fires once per rule firing, not once per
    # recipient — posting inside the loop above would duplicate the message
    # N times for N resolved users.
    slack_sent = 0
    if "slack" in channels:
        integrations = (
            db.query(Integration)
            .filter(
                Integration.organization_id == org_id,
                Integration.type == "slack",
                Integration.is_active.is_(True),
            )
            .all()
        )
        if not integrations:
            channel_errors.append("slack: no active Slack integration configured")

        title = f"Automation: {rule.name}"
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{title}*\n{message_template}"},
            }
        ]
        if feedback is not None:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Feedback #{feedback.id}"}
                    ],
                }
            )

        for integration in integrations:
            webhook_url = (integration.config or {}).get("webhook_url")
            if not webhook_url:
                channel_errors.append(
                    f"slack: integration {integration.id} has no webhook_url"
                )
                continue

            try:
                send_slack_message_webhook(
                    webhook_url=webhook_url, blocks=blocks, text=title
                )
                slack_sent += 1
            except Exception as exc:
                logger.warning(
                    "automation_feedback_trigger: slack notify failed for integration %s: %s",
                    integration.id, exc,
                )
                channel_errors.append(f"slack: integration {integration.id}: {exc}")

    # Loudness: any channel string outside the known set is a silent drop
    # unless we log and record it here.
    for ch in channels:
        if ch not in KNOWN_NOTIFY_CHANNELS:
            logger.warning(
                "automation_feedback_trigger: unknown notification channel %r on rule %s",
                ch, rule.id,
            )
            channel_errors.append(f"unknown channel: {ch}")

    return {
        "type": "send_notification",
        "result": {"notifications_created": created_count, "slack_sent": slack_sent},
        "error": "; ".join(channel_errors) if channel_errors else None,
    }


def _execute_draft_response(
    config: dict, feedback: Optional[FeedbackItem], db: Session
) -> Dict:
    """
    Generate an AI draft response as a canned, tone-aware template.

    Mirrors AutomationEngine._execute_draft_response. `FeedbackResponse` is
    NOT mirrored in worker-service (same gap `playbook_engine._handle_draft_response`
    already works around) — persisting is best-effort: if the model isn't
    available, the draft is still generated and the action still succeeds.
    """
    if feedback is None:
        return {"type": "draft_response", "result": None, "error": "No feedback object"}

    tone: str = config.get("tone", "professional")

    draft_text = (
        f"Thank you for reaching out. We have received your feedback and appreciate "
        f"you taking the time to share your experience with us. A member of our team "
        f"will review this and follow up shortly.\n\n"
        f"[Tone: {tone}]"
    )

    try:
        from src.models import FeedbackResponse  # type: ignore[attr-defined]

        response = FeedbackResponse(
            feedback_id=feedback.id,
            organization_id=feedback.organization_id,
            user_id=None,
            response_text=draft_text,
            channel="clipboard",
            source="ai_generated",
            tone=tone,
            status="draft",
        )
        db.add(response)
    except (ImportError, AttributeError):
        logger.debug(
            "automation_feedback_trigger: FeedbackResponse not available in worker context"
        )

    return {
        "type": "draft_response",
        "result": {"tone": tone, "length": len(draft_text)},
        "error": None,
    }
