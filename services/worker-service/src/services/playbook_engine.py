"""
Playbook execution engine — Phase 5.2 (M4.1).

Pure business logic called by the Celery task `tasks.churn_playbooks.run_playbook`.
No Celery dependency here — fully testable with a plain SQLAlchemy session.

Public API:
    execute(execution_id: int, db: Session) -> dict
        Run a ChurnPlaybookExecution. Idempotent: skips if not in 'queued' state.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.models import (
    ChurnPlaybook,
    ChurnPlaybookExecution,
    CustomerHealth,
)
from src.tasks.intercom_writeback import push_resolved_writeback

logger = logging.getLogger(__name__)

# Rate-limit window: same (playbook_id, customer_email) within 60 minutes
_RATE_LIMIT_MINUTES = 60

# Retention: purge executions older than 90 days
EXECUTION_RETENTION_DAYS = 90


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def execute(execution_id: int, db: Session) -> dict:
    """
    Execute a ChurnPlaybookExecution by id.

    Returns a dict with either:
        {"skipped": True, "reason": "..."}   — if already running/done/cancelled
        {"status": "done"|"failed"|"cancelled", "action_log": [...]}  — after run
    """
    execution = db.query(ChurnPlaybookExecution).filter_by(id=execution_id).first()
    if execution is None:
        logger.error("playbook_engine.execute: execution %s not found", execution_id)
        return {"skipped": True, "reason": "execution not found"}

    # Idempotency guard
    if execution.status != "queued":
        return {"skipped": True, "reason": f"status is already '{execution.status}'"}

    # Per-(playbook, customer) rate-limit: 60-minute window
    if _is_rate_limited(execution, db):
        execution.status = "cancelled"
        execution.error_message = "rate-limited: same playbook ran for this customer within 60 minutes"
        execution.completed_at = datetime.utcnow()
        db.commit()
        return {"status": "cancelled", "action_log": []}

    # Mark running
    execution.status = "running"
    execution.started_at = datetime.utcnow()
    db.commit()

    # Load playbook
    playbook = db.query(ChurnPlaybook).filter_by(id=execution.playbook_id).first()
    if playbook is None:
        return _finalize_execution(execution, db, status="failed",
                                   error_message="playbook deleted", action_log=[])

    # Load customer health (for context passed to handlers)
    health = db.query(CustomerHealth).filter_by(
        organization_id=execution.organization_id,
        customer_email=execution.customer_email,
    ).first()
    if health is None:
        logger.warning(
            "playbook_engine: no CustomerHealth for org=%s email=%s",
            execution.organization_id, execution.customer_email,
        )
        return _finalize_execution(execution, db, status="failed",
                                   error_message="customer not found in health scores",
                                   action_log=[])

    # Execute each action, collecting outcomes
    action_log = _run_actions(playbook.action_sequence or [], execution.customer_email, health, db)

    # Determine final status
    any_ok = any(entry.get("ok") for entry in action_log)
    final_status = "done" if any_ok else "failed"

    return _finalize_execution(execution, db, status=final_status, action_log=action_log)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_rate_limited(execution: ChurnPlaybookExecution, db: Session) -> bool:
    """
    Return True if a done/running execution for the same (playbook_id, customer_email)
    was created within the last 60 minutes.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=_RATE_LIMIT_MINUTES)
    existing = (
        db.query(ChurnPlaybookExecution)
        .filter(
            ChurnPlaybookExecution.playbook_id == execution.playbook_id,
            ChurnPlaybookExecution.customer_email == execution.customer_email,
            ChurnPlaybookExecution.id != execution.id,
            ChurnPlaybookExecution.created_at >= cutoff,
            ChurnPlaybookExecution.status.in_(["done", "running"]),
        )
        .first()
    )
    return existing is not None


def _run_actions(
    action_sequence: list,
    customer_email: str,
    health: CustomerHealth,
    db: Session,
) -> list:
    """
    Execute each action dict in sequence. Continues past failures.
    Returns action_log: [{type, ok, result|None, error|None}, ...].
    """
    log = []
    for action in action_sequence:
        action_type: str = action.get("type", "")
        action_config: dict = action.get("config", {})
        try:
            outcome = _dispatch_action(action_type, action_config, customer_email, health, db)
            log.append({
                "type": action_type,
                "ok": outcome.get("ok", True),
                "result": outcome.get("result"),
                "error": outcome.get("error"),
            })
        except Exception as exc:
            logger.exception(
                "playbook_engine: action '%s' raised for customer %s: %s",
                action_type, customer_email, exc,
            )
            log.append({"type": action_type, "ok": False, "result": None, "error": str(exc)})
    return log


def _dispatch_action(
    action_type: str,
    action_config: dict,
    customer_email: str,
    health: CustomerHealth,
    db: Session,
) -> dict:
    """
    Dispatch an action to the appropriate handler.

    Reuses logic from the existing automation handlers (re-implemented here
    for the worker-service context — the backend-api AutomationEngine is not
    importable from the worker).

    Supported types: assign, change_status, send_notification, draft_response,
    send_email.
    Unknown types return ok=False with an 'unsupported action type' error.
    """
    if action_type == "assign":
        return _handle_assign(action_config, customer_email, health, db)
    elif action_type == "change_status":
        return _handle_change_status(action_config, customer_email, health, db)
    elif action_type == "send_notification":
        return _handle_send_notification(action_config, customer_email, health, db)
    elif action_type == "draft_response":
        return _handle_draft_response(action_config, customer_email, health, db)
    elif action_type == "send_email":
        return _handle_send_email(action_config, customer_email, health, db)
    else:
        return {
            "ok": False,
            "result": None,
            "error": f"unsupported action type: '{action_type}'",
        }


def _handle_assign(
    config: dict, customer_email: str, health: CustomerHealth, db: Session
) -> dict:
    """
    Assign the customer's most recent feedback item to a user or role.

    assign_to values:
      "user:{id}"    → specific user in the org
      "role:owner"   → first owner in org
      "role:admin"   → first admin in org
      "round_robin"  → member with fewest open items (default)
    """
    from src.models import User, FeedbackItem
    from sqlalchemy import func

    org_id = health.organization_id
    assign_to: str = config.get("assign_to", "round_robin")

    # Get most recent feedback for this customer
    feedback = (
        db.query(FeedbackItem)
        .filter_by(organization_id=org_id, customer_email=customer_email)
        .order_by(FeedbackItem.created_at.desc())
        .first()
    )
    if feedback is None:
        return {"ok": False, "result": None, "error": "no feedback found for customer"}

    assigned_id = None

    if assign_to.startswith("user:"):
        try:
            user_id = int(assign_to.split(":")[1])
            user = db.query(User).filter_by(id=user_id, organization_id=org_id).first()
            if user:
                assigned_id = user.id
        except (ValueError, IndexError):
            pass
    elif assign_to.startswith("role:"):
        role = assign_to.split(":")[1]
        user = db.query(User).filter_by(organization_id=org_id, role=role).first()
        if user:
            assigned_id = user.id
    else:
        # Round-robin: member with fewest open items
        open_count = (
            db.query(FeedbackItem.assigned_to, func.count(FeedbackItem.id).label("cnt"))
            .filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.workflow_status.in_(["new", "in_review"]),
                FeedbackItem.assigned_to.isnot(None),
            )
            .group_by(FeedbackItem.assigned_to)
            .subquery()
        )
        member = (
            db.query(User.id, func.coalesce(open_count.c.cnt, 0).label("c"))
            .outerjoin(open_count, User.id == open_count.c.assigned_to)
            .filter(User.organization_id == org_id)
            .order_by(func.coalesce(open_count.c.cnt, 0).asc(), User.id.asc())
            .first()
        )
        if member:
            assigned_id = member.id

    if assigned_id:
        feedback.assigned_to = assigned_id

    return {"ok": True, "result": {"assigned_to": assigned_id}}


def _handle_change_status(
    config: dict, customer_email: str, health: CustomerHealth, db: Session
) -> dict:
    """Update workflow_status on the customer's most recent feedback item."""
    from src.models import FeedbackItem

    org_id = health.organization_id
    new_status: str = config.get("status", "in_review")

    feedback = (
        db.query(FeedbackItem)
        .filter_by(organization_id=org_id, customer_email=customer_email)
        .order_by(FeedbackItem.created_at.desc())
        .first()
    )
    if feedback is None:
        return {"ok": False, "result": None, "error": "no feedback found for customer"}

    old_status = feedback.workflow_status
    feedback.workflow_status = new_status
    if (
        new_status == "resolved"
        and old_status != new_status
        and feedback.source == "intercom"
    ):
        push_resolved_writeback.delay(
            org_id, [{"id": feedback.id, "resolution_note": None}],
        )
    return {"ok": True, "result": {"old_status": old_status, "new_status": new_status}}


def _handle_send_notification(
    config: dict, customer_email: str, health: CustomerHealth, db: Session
) -> dict:
    """
    Create in-app notifications for configured recipients.

    recipients: "admins" | "owner" | "assignee" | "user:{id}"
    """
    from src.models import User, Notification

    org_id = health.organization_id
    recipients: str = config.get("recipients", "admins")
    title: str = config.get("title", "Churn playbook triggered")
    message: str = config.get(
        "message",
        f"A churn prevention playbook was triggered for customer {customer_email}.",
    )

    target_ids = []
    if recipients == "admins":
        users = db.query(User).filter(
            User.organization_id == org_id,
            User.role.in_(["admin", "owner"]),
        ).all()
        target_ids = [u.id for u in users]
    elif recipients == "owner":
        users = db.query(User).filter_by(organization_id=org_id, role="owner").all()
        target_ids = [u.id for u in users]
    elif recipients.startswith("user:"):
        try:
            target_ids = [int(recipients.split(":")[1])]
        except (ValueError, IndexError):
            pass

    created = 0
    for uid in target_ids:
        notif = Notification(
            user_id=uid,
            organization_id=org_id,
            type="playbook_trigger",
            title=title,
            message=message,
            link=f"/customers/{customer_email}",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db.add(notif)
        created += 1

    return {"ok": True, "result": {"notifications_created": created}}


def _handle_draft_response(
    config: dict, customer_email: str, health: CustomerHealth, db: Session
) -> dict:
    """
    Generate a canned AI draft response on the customer's most recent feedback.
    Mirrors AutomationEngine._execute_draft_response behavior.
    """
    from src.models import FeedbackItem

    org_id = health.organization_id
    tone: str = config.get("tone", "professional")

    feedback = (
        db.query(FeedbackItem)
        .filter_by(organization_id=org_id, customer_email=customer_email)
        .order_by(FeedbackItem.created_at.desc())
        .first()
    )
    if feedback is None:
        return {"ok": False, "result": None, "error": "no feedback found for customer"}

    draft_text = (
        f"Thank you for reaching out. We value your feedback and want to ensure we "
        f"address your concerns promptly. A member of our team will be in touch soon.\n\n"
        f"[Tone: {tone}]"
    )

    # Attempt to persist a FeedbackResponse if the model is available
    try:
        from src.models import FeedbackResponse  # type: ignore[import]
        response = FeedbackResponse(
            feedback_id=feedback.id,
            organization_id=org_id,
            user_id=None,
            response_text=draft_text,
            channel="clipboard",
            source="ai_generated",
            tone=tone,
            status="draft",
        )
        db.add(response)
    except (ImportError, AttributeError):
        # FeedbackResponse not mirrored in worker — log and continue
        logger.debug("draft_response: FeedbackResponse not available in worker context")

    return {"ok": True, "result": {"tone": tone, "length": len(draft_text)}}


def _handle_send_email(
    config: dict, customer_email: str, health: CustomerHealth, db: Session
) -> dict:
    """
    Send an outreach email from a built-in registry template.

    recipients:
      "customer"    → the playbook execution's customer_email
      "cs_assignee" → the email of the customer's assigned CS owner

    The actual send — opt-out check, cooldown, List-Unsubscribe, Resend call —
    lives in `src.services.outreach_sender.send_outreach_email` (outreach-core);
    this handler validates config, resolves the recipient, renders the registry
    template (real worker mirror, never mocked) and maps the sender's result
    loudly. Only `status == "sent"` contributes ok=True — a skip or failure is
    recorded in the action_log, never a false success.
    """
    from src.models import Organization, User
    from src.services.outreach_templates_mirror import (
        OUTREACH_TEMPLATES,
        render_outreach_template,
    )
    from src.services.outreach_sender import send_outreach_email

    template = config.get("template")
    if not template:
        return {
            "ok": False,
            "result": None,
            "error": "send_email step missing 'template' in config",
        }

    recipient = config.get("recipient")
    if not recipient:
        return {
            "ok": False,
            "result": None,
            "error": "send_email step missing 'recipient' in config",
        }

    org_id = health.organization_id

    if recipient == "customer":
        to_email = customer_email
    elif recipient == "cs_assignee":
        owner_id = health.cs_owner_user_id
        if owner_id is None:
            return {
                "ok": False,
                "result": None,
                "error": (
                    "cs_assignee recipient requested but customer has no "
                    "assigned CS owner"
                ),
            }
        owner_email = db.query(User.email).filter(User.id == owner_id).first()
        if not owner_email or not owner_email[0]:
            return {
                "ok": False,
                "result": None,
                "error": f"cs_assignee user {owner_id} not found",
            }
        to_email = owner_email[0]
    else:
        return {
            "ok": False,
            "result": None,
            "error": f"unsupported send_email recipient: '{recipient}'",
        }

    org = db.query(Organization).filter_by(id=org_id).first()
    product_name = (
        org.product_name_display if org and org.product_name_display else "Rereflect"
    )
    customer_name = health.customer_name or customer_email.split("@")[0]

    try:
        tpl = OUTREACH_TEMPLATES[template]
    except KeyError:
        return {
            "ok": False,
            "result": None,
            "error": f"unknown outreach template: '{template}'",
        }
    body = render_outreach_template(template, customer_name, product_name)
    subject = (
        tpl.subject
        .replace("{{CUSTOMER_NAME}}", customer_name)
        .replace("{{PRODUCT_NAME}}", product_name)
    )

    result = send_outreach_email(
        db,
        org_id,
        to_email,
        subject,
        body,
        product_name=product_name,
        template_key=template,
    )
    return {
        "ok": result.get("status") == "sent",
        "result": {
            "status": result.get("status"),
            "reason": result.get("reason"),
            "to": to_email,
            "template": template,
        },
        "error": None,
    }


def _finalize_execution(
    execution: ChurnPlaybookExecution,
    db: Session,
    *,
    status: str,
    action_log: list = None,
    error_message: str = None,
) -> dict:
    """Persist final status, completed_at, action_log, and commit."""
    execution.status = status
    execution.completed_at = datetime.utcnow()
    if action_log is not None:
        execution.action_log = action_log
    if error_message is not None:
        execution.error_message = error_message
    db.commit()
    return {"status": status, "action_log": action_log or []}
