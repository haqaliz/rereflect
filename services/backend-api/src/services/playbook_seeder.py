"""
Playbook template seeder (M4.1 Phase 5.1).

Idempotent — safe to call on every startup. Inserts the 7 pre-built system
templates defined in SEED_TEMPLATES if they don't already exist (matched by
name).  Templates have organization_id=NULL and is_template=True.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from src.models.churn_playbook import ChurnPlaybook

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed action types (union of Automations + playbook-specific taxonomy)
# ---------------------------------------------------------------------------

VALID_ACTION_TYPES = frozenset({
    "assign",
    "notify",
    "draft_response",
    "send_email",
    "tag",
    "schedule_task",
    "create_task",
    "trigger_automation",
    "auto_assign",
    "change_status",
    "send_notification",
})

# ---------------------------------------------------------------------------
# Seed data — 7 templates per PRD §4.5
# ---------------------------------------------------------------------------

SEED_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "Critical Save",
        "description": (
            "For customers with a very high churn probability (85–100%). "
            "Assigns to CS lead, fires a Slack alert, and drafts an urgent response."
        ),
        "probability_min": 0.85,
        "probability_max": 1.00,
        "action_sequence": [
            {
                "type": "assign",
                "config": {"role": "cs_lead", "strategy": "round_robin"},
            },
            {
                "type": "notify",
                "config": {
                    "channel": "slack",
                    "target": "#cs-leads",
                    "message": "Critical churn risk detected — immediate action required.",
                },
            },
            {
                "type": "send_notification",
                "config": {
                    "recipients": "admins",
                    "channels": ["dashboard"],
                    "priority": "urgent",
                },
            },
            {
                "type": "draft_response",
                "config": {"tone": "empathetic", "template_hint": "critical_save"},
            },
        ],
    },
    {
        "name": "Churn Prevention",
        "description": (
            "For customers with a high churn probability (70–85%). "
            "Assigns to the customer's CS owner (or round-robin) and schedules a check-in."
        ),
        "probability_min": 0.70,
        "probability_max": 0.85,
        "action_sequence": [
            {
                "type": "assign",
                "config": {"strategy": "assigned_owner_or_round_robin"},
            },
            {
                "type": "draft_response",
                "config": {"tone": "empathetic", "template_hint": "churn_prevention"},
            },
            {
                "type": "schedule_task",
                "config": {"description": "Follow-up check-in", "due_in_days": 3},
            },
        ],
    },
    {
        "name": "At-Risk Outreach",
        "description": (
            "For customers with a moderate-high churn probability (50–70%). "
            "Tags the customer and notifies their assignee."
        ),
        "probability_min": 0.50,
        "probability_max": 0.70,
        "action_sequence": [
            {
                "type": "send_email",
                "config": {"template": "weekly_digest_entry", "recipient": "cs_assignee"},
            },
            {
                "type": "tag",
                "config": {"tag": "at-risk"},
            },
            {
                "type": "send_notification",
                "config": {
                    "recipients": "assignee",
                    "channels": ["dashboard"],
                    "message": "Customer flagged as at-risk.",
                },
            },
        ],
    },
    {
        "name": "Light-Touch Nudge",
        "description": (
            "For customers with a low-moderate churn probability (30–50%). "
            "Tags for monitoring and queues for weekly review."
        ),
        "probability_min": 0.30,
        "probability_max": 0.50,
        "action_sequence": [
            {
                "type": "tag",
                "config": {"tag": "monitor"},
            },
            {
                "type": "create_task",
                "config": {
                    "description": "Add to weekly review queue",
                    "due_in_days": 7,
                    "priority": "low",
                },
            },
        ],
    },
    {
        "name": "Power-User Recovery",
        "description": (
            "For high-volume customers with elevated churn probability (50–100%). "
            "Escalates to exec channel and drafts a personalized response."
        ),
        "probability_min": 0.50,
        "probability_max": 1.00,
        "action_sequence": [
            {
                "type": "notify",
                "config": {
                    "channel": "slack",
                    "target": "#exec-alerts",
                    "message": "Power user at churn risk — escalation needed.",
                },
            },
            {
                "type": "draft_response",
                "config": {"tone": "empathetic", "template_hint": "power_user_recovery", "personalized": True},
            },
            {
                "type": "create_task",
                "config": {
                    "description": "High-priority follow-up with power user",
                    "priority": "high",
                    "due_in_days": 1,
                },
            },
        ],
    },
    {
        "name": "New-Customer Save",
        "description": (
            "For recently acquired customers (< 1 month) with elevated churn probability (40–100%). "
            "Triggers onboarding flow and assigns to CS."
        ),
        "probability_min": 0.40,
        "probability_max": 1.00,
        "action_sequence": [
            {
                "type": "trigger_automation",
                "config": {"automation_name": "onboarding_playbook"},
            },
            {
                "type": "assign",
                "config": {"role": "cs_lead", "strategy": "round_robin"},
            },
            {
                "type": "draft_response",
                "config": {"tone": "friendly", "template_hint": "welcome_and_save"},
            },
        ],
    },
    {
        "name": "Silent-Churn Watch",
        "description": (
            "Manual-trigger playbook for customers showing signs of silent churn. "
            "Sends a re-engagement email and flags for follow-up in 14 days."
        ),
        "probability_min": 0.00,
        "probability_max": 1.00,
        "action_sequence": [
            {
                "type": "send_email",
                "config": {"template": "re_engagement", "recipient": "customer"},
            },
            {
                "type": "create_task",
                "config": {
                    "description": "Follow-up: confirm engagement or mark silent churn",
                    "due_in_days": 14,
                    "priority": "medium",
                },
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------


def seed_playbook_templates(db: Session) -> None:
    """Insert SEED_TEMPLATES as system templates if they don't exist yet.

    Idempotent: matched by name + is_template=True. Skips existing records.
    """
    created = 0
    for tmpl_data in SEED_TEMPLATES:
        exists = (
            db.query(ChurnPlaybook)
            .filter(
                ChurnPlaybook.name == tmpl_data["name"],
                ChurnPlaybook.is_template.is_(True),
            )
            .first()
        )
        if exists:
            continue

        tmpl = ChurnPlaybook(
            organization_id=None,
            name=tmpl_data["name"],
            description=tmpl_data.get("description"),
            probability_min=tmpl_data["probability_min"],
            probability_max=tmpl_data["probability_max"],
            action_sequence=tmpl_data["action_sequence"],
            is_template=True,
            is_active=True,
        )
        db.add(tmpl)
        created += 1

    if created:
        db.commit()
        logger.info(f"Playbook seeder: created {created} system templates.")
    else:
        logger.info("Playbook seeder: all templates already present, skipping.")
