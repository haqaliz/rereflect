"""
Pre-built automation rule templates (M4.4 — Phase 1).

5 starter templates users can enable and customize from Settings > Automations.
Each template is a dict that maps directly to the AutomationRule schema so it
can be instantiated with a single call.
"""

from typing import Any

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

AUTOMATION_TEMPLATES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ #
    # 1. Churn Prevention
    # ------------------------------------------------------------------ #
    {
        "id": "churn_prevention",
        "name": "Churn Prevention",
        "description": (
            "Automatically escalate customers whose health score drops below 30. "
            "Assigns to an admin, notifies via dashboard and email, and drafts an empathetic response."
        ),
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 30, "direction": "below"},
        },
        "actions": [
            {"type": "auto_assign", "config": {"assign_to": "round_robin"}},
            {
                "type": "send_notification",
                "config": {"recipients": "admins", "channels": ["dashboard", "email"]},
            },
            {"type": "draft_response", "config": {"tone": "empathetic"}},
        ],
        "cooldown_hours": 48,
    },

    # ------------------------------------------------------------------ #
    # 2. Critical Bug Escalation
    # ------------------------------------------------------------------ #
    {
        "id": "critical_bug_escalation",
        "name": "Critical Bug Escalation",
        "description": (
            "Escalate critical bugs and security breaches immediately. "
            "Assigns to an admin, sets status to In Review, and notifies all channels."
        ),
        "trigger": {
            "type": "feedback_category_match",
            "config": {
                "categories": ["critical_bug", "security_breach"],
                "is_urgent": True,
            },
        },
        "actions": [
            {"type": "auto_assign", "config": {"assign_to": "role:admin"}},
            {"type": "change_status", "config": {"status": "in_review"}},
            {
                "type": "send_notification",
                "config": {
                    "recipients": "admins",
                    "channels": ["dashboard", "email", "slack"],
                },
            },
        ],
        "cooldown_hours": 1,
    },

    # ------------------------------------------------------------------ #
    # 3. Feature Request Triage
    # ------------------------------------------------------------------ #
    {
        "id": "feature_request_triage",
        "name": "Feature Request Triage",
        "description": (
            "Automatically triage incoming feature requests by setting their status "
            "to In Review and assigning them via round-robin."
        ),
        "trigger": {
            "type": "feedback_category_match",
            "config": {"categories": ["feature_request"]},
        },
        "actions": [
            {"type": "change_status", "config": {"status": "in_review"}},
            {"type": "auto_assign", "config": {"assign_to": "round_robin"}},
        ],
        "cooldown_hours": 24,
    },

    # ------------------------------------------------------------------ #
    # 4. Negative Sentiment Alert
    # ------------------------------------------------------------------ #
    {
        "id": "negative_sentiment_alert",
        "name": "Negative Sentiment Alert",
        "description": (
            "Alert the team when a customer sends 3 or more negative feedbacks "
            "within 7 days. Notifies admins and drafts an empathetic response."
        ),
        "trigger": {
            "type": "sentiment_pattern",
            "config": {"count": 3, "days": 7, "sentiment": "negative"},
        },
        "actions": [
            {
                "type": "send_notification",
                "config": {"recipients": "admins", "channels": ["dashboard", "email"]},
            },
            {"type": "draft_response", "config": {"tone": "empathetic"}},
        ],
        "cooldown_hours": 48,
    },

    # ------------------------------------------------------------------ #
    # 5. Positive Feedback Follow-up
    # ------------------------------------------------------------------ #
    {
        "id": "positive_feedback_followup",
        "name": "Positive Feedback Follow-up",
        "description": (
            "Draft a friendly thank-you response whenever a customer leaves "
            "positive feedback. Cooldown of 1 week prevents over-messaging."
        ),
        "trigger": {
            "type": "feedback_category_match",
            "config": {"categories": ["positive"]},
        },
        "actions": [
            {"type": "draft_response", "config": {"tone": "friendly"}},
        ],
        "cooldown_hours": 168,  # 1 week
    },
]

# Quick lookup by id
TEMPLATES_BY_ID: dict[str, dict[str, Any]] = {t["id"]: t for t in AUTOMATION_TEMPLATES}
