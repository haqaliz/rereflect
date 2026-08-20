"""
Pre-built automation rule templates (M4.4 — Phase 1; template 6 added by
usage-trend-automation-trigger's template-and-docs aspect, M10; template 7
added by batch-sentiment-trigger, Track A; template 8 added by
automation-send-customer-email — the first template whose action emails the
CUSTOMER rather than the team).

8 starter templates users can enable and customize from Settings > Automations.
Each template is a dict that maps directly to the AutomationRule schema so it
can be instantiated with a single call.

Optional `mode` key (M10): honored by `enable_template`
(`api/routes/automations.py`), defaults to "active" when absent so the
original 5 templates are unaffected. Templates 6 and 7 set it, to "shadow" —
`usage_trend` and `batch_sentiment_threshold` rules default to shadow
everywhere else in the product (M7 / batch-sentiment-trigger) and a template
that silently armed itself would be the one exception. Template 8 sets it for
a sharper reason: its action sends a customer-facing email, so an armed-on-
enable template would mail real customers on the strength of one click.
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

    # ------------------------------------------------------------------ #
    # 6. Usage Decline Outreach (usage-trend-automation-trigger, M10)
    # ------------------------------------------------------------------ #
    {
        "id": "usage_decline_outreach",
        "name": "Usage Decline Outreach",
        "description": (
            "Notify admins when a customer's product-usage trend worsens "
            "into 'declining' or 'sharp_decline' (the usage_trend trigger). "
            "Starts in shadow mode, so the execution log fills with "
            "would-have-fired entries for you to review before you flip it "
            "to active. This template ships a send_notification action "
            "only, NOT run_playbook: a playbook's id is a per-install "
            "autoincrement integer this static template can't know ahead "
            "of time. To wire this into your at-risk save motion, edit the "
            "rule after enabling it and add a run_playbook action pointing "
            "at your own playbook (Settings > Automations)."
        ),
        "trigger": {
            "type": "usage_trend",
            "config": {"states": ["declining", "sharp_decline"]},
        },
        "actions": [
            {
                "type": "send_notification",
                "config": {"recipients": "admins", "channels": ["dashboard", "email"]},
            },
        ],
        "cooldown_hours": 24,
        "mode": "shadow",
    },

    # ------------------------------------------------------------------ #
    # 7. Batch Sentiment Alert (batch-sentiment-trigger, Track A)
    # ------------------------------------------------------------------ #
    {
        "id": "batch_sentiment_alert",
        "name": "Batch Sentiment Alert",
        "description": (
            "Notify admins when incoming feedback as a whole crosses a "
            "negative-sentiment threshold within a rolling window (the "
            "batch_sentiment_threshold trigger) — distinct from "
            "sentiment_pattern, which watches a single customer. Starts in "
            "shadow mode: nobody knows this trigger's firing rate on real "
            "data yet, so the execution log fills with would-have-fired "
            "entries to review before you flip it to active."
        ),
        "trigger": {
            "type": "batch_sentiment_threshold",
            "config": {
                "sentiment": "negative",
                "window_hours": 24,
                "mode": "percentage",
                "threshold": 0.5,
                "min_total": 5,
            },
        },
        "actions": [
            {
                "type": "send_notification",
                "config": {"recipients": "admins", "channels": ["dashboard", "email"]},
            },
        ],
        "cooldown_hours": 24,
        "mode": "shadow",
    },

    # ------------------------------------------------------------------ #
    # 8. At-Risk Customer Outreach (automation-send-customer-email)
    # ------------------------------------------------------------------ #
    {
        "id": "at_risk_customer_outreach",
        "name": "At-Risk Customer Outreach",
        "description": (
            "Email the customer (the re_engagement template) when their churn "
            "probability crosses 0.6 — the automation-rule form of the "
            "at-risk outreach playbook step. Starts in shadow mode so the "
            "execution log fills with would-have-sent entries before you flip "
            "it to active. Opt-out, the per-recipient cooldown and the "
            "tokenized unsubscribe link are honored exactly as on bulk "
            "outreach; with no RESEND_API_KEY configured every execution "
            "records 'skipped: email not configured' rather than a silent "
            "success."
        ),
        "trigger": {
            "type": "churn_probability_threshold",
            # `direction` is accepted-but-inert: the engine always fires on
            # churn_probability >= threshold (automation_engine
            # ._trigger_churn_probability) and seed_churn_cooldowns reads
            # `threshold` only. Kept for shape parity with the API's
            # ChurnProbabilityConfig, which defaults it to "above".
            "config": {"threshold": 0.6, "direction": "above"},
        },
        "actions": [
            {
                "type": "send_customer_email",
                "config": {"template": "re_engagement", "recipient": "customer"},
            },
        ],
        # 24h, deliberately aligned with the OUTREACH_COOLDOWN_HOURS default so
        # the rule's own cooldown does not outlive the shared outreach window.
        "cooldown_hours": 24,
        "mode": "shadow",
    },
]

# Quick lookup by id
TEMPLATES_BY_ID: dict[str, dict[str, Any]] = {t["id"]: t for t in AUTOMATION_TEMPLATES}
