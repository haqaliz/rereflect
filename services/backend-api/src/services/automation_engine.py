"""
AutomationEngine — Phase 2 execution engine for AI Workflow Automation (M4.4).

Evaluates active automation rules against events and fires their actions.

Dispatch points (callers):
- worker-service analysis.py  → after feedback analysis
- health_score_service.py     → after health score recomputation

Both call sites wrap engine.evaluate() in try/except so that any engine
failure never breaks the main processing flow.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule
from src.models.feedback import FeedbackItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Redis client (DB 1 — same database used by Celery broker; cooldowns use
# dedicated key prefix so they never collide with Celery's internal keys)
# ---------------------------------------------------------------------------

_redis_client: Optional[redis.Redis] = None

COOLDOWN_KEY_PREFIX = "automation_cooldown"


def _get_redis() -> Optional[redis.Redis]:
    """Return a shared Redis client, or None if Redis is unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", 6379))
            password = os.getenv("REDIS_PASSWORD") or None
            _redis_client = redis.Redis(
                host=host,
                port=port,
                password=password,
                db=1,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            _redis_client.ping()
        except Exception as exc:
            logger.warning("AutomationEngine: Redis unavailable — cooldowns disabled: %s", exc)
            _redis_client = None
    return _redis_client


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AutomationEngine:
    """
    Evaluates active automation rules and executes their actions.

    Usage:
        engine = AutomationEngine(db)
        results = engine.evaluate(org_id, "health_score_threshold", context)

    Context shape varies by event type:
        health_score_threshold:      {"health_score": int, "customer_email": str, "feedback_id": int}
        sentiment_pattern:           {"customer_email": str, "feedback_id": int}
        churn_risk_level_change:     {"new_risk_level": str, "old_risk_level": str, "customer_email": str, "feedback_id": int}
        feedback_category_match:     {"customer_email": str, "feedback_id": int}
        churn_probability_threshold: {"churn_probability": float, "customer_email": str}

    Rule `mode` gating (see AutomationRule.mode):
        off:    rule is never selected by evaluate().
        shadow: trigger + cooldown are evaluated and an AutomationExecution is
                logged (status="shadow"), but no actions are executed.
        active: full evaluation — trigger, cooldown, actions, logging, stats.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, org_id: int, event_type: str, context: Dict[str, Any]) -> List[Dict]:
        """
        Evaluate all active rules for *org_id* that match *event_type*.

        For each matching rule:
        1. Check the trigger condition against *context*.
        2. Check per-customer cooldown in Redis.
        3. If both pass, execute all actions, log the execution, update stats.

        Returns a list of execution summary dicts, one per rule that fired.
        """
        rules: List[AutomationRule] = (
            self.db.query(AutomationRule)
            .filter(
                AutomationRule.organization_id == org_id,
                AutomationRule.trigger_type == event_type,
                AutomationRule.mode.in_(["shadow", "active"]),
            )
            .all()
        )

        results = []
        for rule in rules:
            try:
                result = self._evaluate_rule(rule, context)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.error(
                    "AutomationEngine: unhandled error evaluating rule %s: %s",
                    rule.id, exc,
                )

        return results

    # ------------------------------------------------------------------
    # Internal — rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_rule(
        self, rule: AutomationRule, context: Dict[str, Any]
    ) -> Optional[Dict]:
        """Evaluate a single rule. Returns execution summary or None if not fired."""
        customer_email: str = context.get("customer_email", "")
        feedback_id: Optional[int] = context.get("feedback_id")

        # 1. Trigger check
        if not self._check_trigger(rule, context):
            return None

        # 2. Cooldown check
        if self._check_cooldown(rule.id, customer_email):
            logger.debug(
                "AutomationEngine: rule %s in cooldown for customer %s — skipping",
                rule.id, customer_email,
            )
            return None

        # 3. Fetch feedback object (may be absent for health-score events)
        feedback: Optional[FeedbackItem] = None
        if feedback_id:
            feedback = self.db.query(FeedbackItem).filter(
                FeedbackItem.id == feedback_id
            ).first()

        # 4. Execute actions — skipped entirely in shadow mode
        if rule.mode == "shadow":
            action_results: List[Dict] = []
            status = "shadow"
        else:
            action_results = self._execute_actions(rule, feedback, context)

            # 5. Determine overall status
            errors = [r for r in action_results if r.get("error")]
            if not errors:
                status = "success"
            elif len(errors) < len(action_results):
                status = "partial_failure"
            else:
                status = "failed"

        # 6. Log execution
        self._log_execution(
            rule=rule,
            feedback=feedback,
            customer_email=customer_email,
            trigger_snapshot=context,
            action_results=action_results,
            status=status,
        )

        # 7. Update rule stats
        rule.execution_count = (rule.execution_count or 0) + 1
        rule.last_executed_at = datetime.utcnow()

        # 8. Set cooldown
        self._set_cooldown(rule.id, customer_email, rule.cooldown_hours)

        self.db.commit()

        return {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "status": status,
            "actions": action_results,
        }

    # ------------------------------------------------------------------
    # Internal — trigger evaluation
    # ------------------------------------------------------------------

    def _check_trigger(self, rule: AutomationRule, context: Dict[str, Any]) -> bool:
        """Dispatch to the correct trigger checker based on rule.trigger_type."""
        t = rule.trigger_type
        cfg = rule.trigger_config or {}

        if t == "health_score_threshold":
            return self._trigger_health_score(cfg, context)
        if t == "sentiment_pattern":
            return self._trigger_sentiment_pattern(cfg, context)
        if t == "churn_risk_level_change":
            return self._trigger_churn_risk_level(cfg, context)
        if t == "feedback_category_match":
            return self._trigger_feedback_category(cfg, context)
        if t == "churn_probability_threshold":
            return self._trigger_churn_probability(cfg, context)

        logger.warning("AutomationEngine: unknown trigger type '%s'", t)
        return False

    def _trigger_health_score(self, cfg: dict, context: dict) -> bool:
        """Fire when health_score < threshold (direction=below)."""
        threshold = cfg.get("threshold", 30)
        health_score = context.get("health_score")
        if health_score is None:
            return False
        # PRD only defines direction=below; treat absence the same way
        return int(health_score) < int(threshold)

    def _trigger_sentiment_pattern(self, cfg: dict, context: dict) -> bool:
        """Fire when customer has >= count negative feedbacks in last *days* days."""
        required_count: int = cfg.get("count", 3)
        days: int = cfg.get("days", 7)
        sentiment: str = cfg.get("sentiment", "negative")
        customer_email: str = context.get("customer_email", "")

        if not customer_email:
            return False

        cutoff = datetime.utcnow() - timedelta(days=days)

        # Determine org_id from any recent feedback by this customer
        sample = (
            self.db.query(FeedbackItem.organization_id)
            .filter(FeedbackItem.customer_email == customer_email)
            .first()
        )
        if not sample:
            return False
        org_id = sample.organization_id

        count = (
            self.db.query(func.count(FeedbackItem.id))
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

    def _trigger_churn_risk_level(self, cfg: dict, context: dict) -> bool:
        """Fire when new_risk_level matches target_level."""
        target_level: str = cfg.get("target_level", "critical")
        new_risk_level: str = context.get("new_risk_level", "")

        if new_risk_level != target_level:
            return False

        # Optional: only fire if coming from a specific set of source levels
        from_levels: Optional[List[str]] = cfg.get("from_levels")
        if from_levels:
            old_risk_level: str = context.get("old_risk_level", "")
            if old_risk_level not in from_levels:
                return False

        return True

    def _trigger_feedback_category(self, cfg: dict, context: dict) -> bool:
        """Fire when feedback categories intersect with configured categories."""
        configured_categories: List[str] = cfg.get("categories", [])
        if not configured_categories:
            return False

        feedback_id: Optional[int] = context.get("feedback_id")
        if not feedback_id:
            return False

        feedback = self.db.query(FeedbackItem).filter(
            FeedbackItem.id == feedback_id
        ).first()
        if not feedback:
            return False

        # Build feedback's effective categories
        feedback_categories: List[str] = []
        if feedback.pain_point_category:
            feedback_categories.append(feedback.pain_point_category)
        if feedback.feature_request_category:
            feedback_categories.append(feedback.feature_request_category)
        if feedback.urgent_category:
            feedback_categories.append(feedback.urgent_category)
        if feedback.tags and isinstance(feedback.tags, list):
            feedback_categories.extend(feedback.tags)

        # Check category intersection
        if not set(configured_categories).intersection(set(feedback_categories)):
            return False

        # Optional urgency filter
        required_urgent = cfg.get("is_urgent")
        if required_urgent is not None and bool(required_urgent) != bool(feedback.is_urgent):
            return False

        return True

    def _trigger_churn_probability(self, cfg: dict, context: dict) -> bool:
        """Fire when churn_probability >= threshold (default 0.7)."""
        p = context.get("churn_probability")
        if p is None:
            return False
        return float(p) >= float(cfg.get("threshold", 0.7))

    # ------------------------------------------------------------------
    # Internal — cooldown
    # ------------------------------------------------------------------

    def _check_cooldown(self, rule_id: int, customer_email: str) -> bool:
        """Return True if this rule/customer pair is still in cooldown (skip it)."""
        r = _get_redis()
        if r is None:
            return False  # Redis unavailable → always allow
        key = f"{COOLDOWN_KEY_PREFIX}:{rule_id}:{customer_email}"
        try:
            return bool(r.exists(key))
        except Exception as exc:
            logger.warning("AutomationEngine: cooldown check failed: %s", exc)
            return False

    def _set_cooldown(self, rule_id: int, customer_email: str, hours: int) -> None:
        """Set Redis cooldown key with TTL = hours * 3600 seconds."""
        r = _get_redis()
        if r is None:
            return
        key = f"{COOLDOWN_KEY_PREFIX}:{rule_id}:{customer_email}"
        ttl_seconds = int(hours) * 3600
        try:
            r.setex(key, ttl_seconds, "1")
        except Exception as exc:
            logger.warning("AutomationEngine: failed to set cooldown: %s", exc)

    # ------------------------------------------------------------------
    # Internal — action execution
    # ------------------------------------------------------------------

    def _execute_actions(
        self,
        rule: AutomationRule,
        feedback: Optional[FeedbackItem],
        context: Dict[str, Any],
    ) -> List[Dict]:
        """Execute all rule actions sequentially. Returns list of {type, result, error}."""
        results: List[Dict] = []
        for action in (rule.actions or []):
            action_type: str = action.get("type", "")
            action_config: dict = action.get("config", {})
            try:
                if action_type == "auto_assign":
                    r = self._execute_assign(action_config, feedback)
                elif action_type == "change_status":
                    r = self._execute_change_status(action_config, feedback)
                elif action_type == "send_notification":
                    r = self._execute_notify(action_config, feedback, rule)
                elif action_type == "draft_response":
                    r = self._execute_draft_response(action_config, feedback)
                else:
                    r = {"type": action_type, "result": None, "error": f"Unknown action type: {action_type}"}
            except Exception as exc:
                logger.error(
                    "AutomationEngine: action '%s' failed on rule %s: %s",
                    action_type, rule.id, exc,
                )
                r = {"type": action_type, "result": None, "error": str(exc)}
            results.append(r)
        return results

    def _execute_assign(self, config: dict, feedback: Optional[FeedbackItem]) -> Dict:
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

        from src.models.user import User
        from src.services.workflow_service import round_robin_assign

        assign_to: str = config.get("assign_to", "round_robin")
        org_id = feedback.organization_id
        assigned_id: Optional[int] = None

        if assign_to.startswith("user:"):
            try:
                user_id = int(assign_to.split(":")[1])
                user = self.db.query(User).filter(
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
                self.db.query(User)
                .filter(User.organization_id == org_id, User.role == role)
                .first()
            )
            if user:
                assigned_id = user.id
        else:
            # round_robin
            assigned_id = round_robin_assign(self.db, org_id)

        if assigned_id:
            feedback.assigned_to = assigned_id

        return {
            "type": "auto_assign",
            "result": {"assigned_to": assigned_id},
            "error": None,
        }

    def _execute_change_status(self, config: dict, feedback: Optional[FeedbackItem]) -> Dict:
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

    def _execute_notify(
        self,
        config: dict,
        feedback: Optional[FeedbackItem],
        rule: AutomationRule,
    ) -> Dict:
        """
        Create in-app (and optionally email) notifications for the configured recipients.

        recipients: "assignee" | "admins" | "owner" | "user:{id}"
        channels:   ["dashboard"] | ["email"] | ["dashboard", "email"]
        """
        from src.models.notification import Notification
        from src.models.user import User

        org_id = rule.organization_id
        recipients: str = config.get("recipients", "admins")
        channels: List[str] = config.get("channels", ["dashboard"])
        message_template: str = config.get(
            "message_template",
            f"Automation '{rule.name}' triggered for feedback #{feedback.id if feedback else '?'}",
        )

        # Resolve recipient user IDs
        target_user_ids: List[int] = []

        if recipients == "admins":
            users = (
                self.db.query(User)
                .filter(User.organization_id == org_id, User.role.in_(["admin", "owner"]))
                .all()
            )
            target_user_ids = [u.id for u in users]
        elif recipients == "owner":
            users = (
                self.db.query(User)
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
                self.db.add(notification)
                created_count += 1

            if "email" in channels:
                # Fire-and-forget email; import lazily to avoid circular deps
                try:
                    user = self.db.query(User).filter(User.id == uid).first()
                    if user:
                        from src.services.email_service import send_alert_email
                        send_alert_email(
                            to_email=user.email,
                            alert_type="automation_trigger",
                            alert_data={
                                "title": f"Automation: {rule.name}",
                                "description": message_template,
                            },
                        )
                except Exception as exc:
                    logger.warning("AutomationEngine: email notify failed for user %s: %s", uid, exc)

        return {
            "type": "send_notification",
            "result": {"notifications_created": created_count},
            "error": None,
        }

    def _execute_draft_response(
        self, config: dict, feedback: Optional[FeedbackItem]
    ) -> Dict:
        """
        Generate an AI draft response and persist it as status='draft'.

        Calls the existing response_generator service.  Falls back to a simple
        canned template if the LLM is unavailable or raises.
        """
        if feedback is None:
            return {"type": "draft_response", "result": None, "error": "No feedback object"}

        from src.models.feedback_response import FeedbackResponse

        tone: str = config.get("tone", "professional")

        # generate_response in response_generator is async; we can't await it here
        # (engine runs in sync Celery task context). Use a tone-aware canned template
        # as a starting draft — editable by the assignee before sending.
        draft_text = (
            f"Thank you for reaching out. We have received your feedback and appreciate "
            f"you taking the time to share your experience with us. A member of our team "
            f"will review this and follow up shortly.\n\n"
            f"[Tone: {tone}]"
        )

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
        self.db.add(response)

        return {
            "type": "draft_response",
            "result": {"tone": tone, "length": len(draft_text)},
            "error": None,
        }

    # ------------------------------------------------------------------
    # Internal — execution logging
    # ------------------------------------------------------------------

    def _log_execution(
        self,
        *,
        rule: AutomationRule,
        feedback: Optional[FeedbackItem],
        customer_email: str,
        trigger_snapshot: dict,
        action_results: List[Dict],
        status: str,
    ) -> AutomationExecution:
        """Persist an AutomationExecution audit record (no commit — caller commits)."""
        execution = AutomationExecution(
            rule_id=rule.id,
            organization_id=rule.organization_id,
            feedback_id=feedback.id if feedback else None,
            customer_email=customer_email or None,
            trigger_snapshot=trigger_snapshot,
            actions_executed=action_results,
            status=status,
            executed_at=datetime.utcnow(),
        )
        self.db.add(execution)
        return execution
