"""
Shared worker-side plumbing for the automation `send_customer_email` action
(automation-send-customer-email, worker-mirrors aspect).

Two things live here:

1. **Delivery-row helpers** — create / load / finish an
   `automation_email_deliveries` row (the worker mirror of the backend model).
2. **`execute_send_customer_email`** — the action handler ALL THREE worker
   evaluator mirrors call (`automation_feedback_trigger`,
   `automation_churn_trigger`, `automation_usage_trend_trigger`).

Why one module instead of three copies: the duplication doctrine in CLAUDE.md
is about the backend↔worker seam (the worker cannot import backend-api), not
about worker-internal code. Three hand-copied handlers would be three chances
to drift on the same process's own semantics, so the mirrors share this one.
The seam that MUST be kept in agreement by discipline is this module vs
backend-api's `AutomationEngine._execute_send_customer_email` — same skip
reasons, same result shape, same rendered subject/body.

The send itself never happens here: this writes a `queued` row and enqueues
`tasks.outreach.send_automation_email`. Opt-out, the tokenized
List-Unsubscribe header, the shared `outreach_cooldown` key and the Resend
call all live in `src.services.outreach_sender` and are never reimplemented.

Every skip is LOUD — an `error` string on the action result and no enqueue,
never a silent success.

Imports are worker-local and plain — no backend imports, no bare `except`
around an import (`tests/test_worker_import_sweep.py`).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src import email as email_module
from src.models import AutomationEmailDelivery, CustomerHealth, Organization, User
from src.models.automation_rule import AutomationRule
from src.services.outreach_templates_mirror import (
    OUTREACH_TEMPLATES,
    render_outreach_template,
)
from src.tasks.outreach import send_automation_email

logger = logging.getLogger(__name__)

# Byte-identical to the backend engine's send_task(...) dispatch string
# (`AutomationEngine._execute_send_customer_email`). A mismatch here is the
# automations-delivery-integrity bug class: the enqueue succeeds and nothing
# ever runs.
AUTOMATION_EMAIL_TASK_NAME = "tasks.outreach.send_automation_email"

# Org-wide evaluators carry this sentinel instead of a customer address
# (`automation_feedback_trigger.ORG_WIDE_COOLDOWN_IDENTITY`). There is nobody
# to email.
ORG_WIDE_IDENTITY = "__org__"

VALID_RECIPIENTS = ("customer", "cs_assignee")

DEFAULT_PRODUCT_NAME = "Rereflect"


# ---------------------------------------------------------------------------
# Delivery-row helpers
# ---------------------------------------------------------------------------

def create_delivery_row(
    db: Session,
    *,
    org_id: int,
    rule_id: int,
    customer_email: str,
    to_email: str,
    template_key: str,
    subject: str,
    body: str,
    status: str = "queued",
    reason: Optional[str] = None,
) -> AutomationEmailDelivery:
    """Insert a delivery row and flush so the caller has its id."""
    row = AutomationEmailDelivery(
        organization_id=org_id,
        rule_id=rule_id,
        customer_email=customer_email,
        to_email=to_email,
        template_key=template_key,
        subject=subject,
        body=body,
        status=status,
        reason=reason,
    )
    db.add(row)
    db.flush()  # id needed for .delay(delivery_id)
    return row


def get_delivery_row(db: Session, delivery_id: int) -> Optional[AutomationEmailDelivery]:
    return (
        db.query(AutomationEmailDelivery)
        .filter(AutomationEmailDelivery.id == delivery_id)
        .first()
    )


def set_delivery_outcome(
    db: Session,
    delivery: AutomationEmailDelivery,
    status: str,
    reason: Optional[str],
) -> None:
    """Write the terminal outcome of a delivery and commit."""
    delivery.status = status
    delivery.reason = reason
    db.commit()


# ---------------------------------------------------------------------------
# The action handler the three mirrors share
# ---------------------------------------------------------------------------

def _err(message: str) -> Dict[str, Any]:
    return {"type": "send_customer_email", "result": None, "error": message}


def execute_send_customer_email(
    config: dict,
    rule: AutomationRule,
    customer_email: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """Queue one automation customer email. Mirrors the backend handler.

    Returns the standard action-result dict so `_evaluate_rule` can compute
    `success` / `partial_failure` / `failed` honestly.
    """
    template_key = config.get("template")
    if template_key not in OUTREACH_TEMPLATES:
        return _err(f"unknown template key: {template_key}")

    recipient = config.get("recipient", "customer")
    if recipient not in VALID_RECIPIENTS:
        return _err(f"unsupported recipient: {recipient}")

    email = (customer_email or "").strip().lower()
    if not email or email == ORG_WIDE_IDENTITY:
        return _err("no customer email (org-wide trigger)")

    health = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == rule.organization_id,
            CustomerHealth.customer_email == email,
        )
        .first()
    )
    # A missing health row is NOT archived (mirrors the sender's
    # missing-row-is-not-opted-out semantics).
    if health is not None and health.is_archived:
        return _err("customer archived")

    if not email_module.RESEND_API_KEY:
        # Loud skip WITH an audit row: "no email key" is the default state of a
        # $0 local install, and an operator needs to see the send never happened.
        create_delivery_row(
            db,
            org_id=rule.organization_id,
            rule_id=rule.id,
            customer_email=email,
            to_email=email,
            template_key=template_key,
            subject="(not rendered — email not configured)",
            body="",
            status="skipped",
            reason="email not configured",
        )
        db.commit()
        return _err("email not configured")

    if recipient == "cs_assignee":
        if health is None:
            return _err("no health row for customer")
        if not health.cs_owner_user_id:
            return _err("no CS owner assigned")
        owner = db.query(User).filter(User.id == health.cs_owner_user_id).first()
        if owner is None or not owner.email:
            return _err("CS owner has no email")
        to_email = owner.email
    else:
        to_email = email

    org = (
        db.query(Organization)
        .filter(Organization.id == rule.organization_id)
        .first()
    )
    product_name = (org.product_name_display if org else None) or DEFAULT_PRODUCT_NAME
    customer_name = (health.customer_name if health else "") or ""

    tpl = OUTREACH_TEMPLATES[template_key]
    # render_outreach_template renders the BODY only — the subject carries its
    # own {{PRODUCT_NAME}} token.
    subject = tpl.subject.replace("{{PRODUCT_NAME}}", product_name)
    body = render_outreach_template(template_key, customer_name, product_name)

    delivery = create_delivery_row(
        db,
        org_id=rule.organization_id,
        rule_id=rule.id,
        customer_email=email,
        to_email=to_email,
        template_key=template_key,
        subject=subject,
        body=body,
    )

    # COMMIT BEFORE PUBLISH. The worker task loads this row by id and wins the
    # race easily — a live run had it log "delivery not found" ~2ms after the
    # publish, leaving the row `queued` forever and sending nothing. The
    # mirrors' own commit happens at the end of _evaluate_rule, far too late.
    db.commit()

    try:
        send_automation_email.delay(delivery.id)
    except Exception as exc:
        # Honest "work accepted, outcome unknown": the row stays `queued` and
        # the deliveries surface shows it. A broker hiccup must not be reported
        # as a failed rule.
        logger.warning(
            "automation_email_delivery: failed to enqueue delivery %s: %s",
            delivery.id, exc,
        )

    return {
        "type": "send_customer_email",
        "result": {"status": "queued", "delivery_id": delivery.id},
        "error": None,
    }
