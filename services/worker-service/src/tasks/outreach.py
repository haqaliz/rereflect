"""
Per-recipient outreach campaign send task (bulk-campaign-api aspect).

    send_outreach_email(campaign_id, recipient_id) — send one outreach email
    via `src.services.outreach_sender.send_outreach_email` (outreach-core's
    helper owns opt-out / cooldown / no-key / List-Unsubscribe checks) and
    record the outcome on the recipient row + campaign status.

The task name string `tasks.outreach.send_outreach_email` is byte-identical
to the backend's dispatch strings (`POST /customers/bulk/outreach` and
`POST /outreach/campaigns/{id}/retry`) — a mismatch is the
automations-delivery-integrity bug class. Imports are worker-local only
(test_worker_import_sweep.py).
"""

import logging

from celery import shared_task

from src.database import get_db_session
from src.models import OutreachCampaign, OutreachCampaignRecipient
from src.services import outreach_sender

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("sent", "skipped", "failed")


@shared_task(bind=True, name="tasks.outreach.send_outreach_email")
def send_outreach_email(self, campaign_id: int, recipient_id: int) -> dict:
    """Send one campaign email to one recipient; never re-raises.

    Returns a result dict:
        {"status": "sent"}                    — sender ok
        {"status": "skipped", "error": ...}   — sender skip (opted out, cooldown)
                                              — or duplicate dispatch of a
                                                terminal recipient
        {"status": "failed", "error": ...}    — sender failure (no key, resend error)
        {"status": "error", "error": ...}     — missing recipient/campaign, task exception
    """
    with get_db_session() as db:
        try:
            return _process_recipient(db, campaign_id, recipient_id)
        except Exception as exc:
            logger.exception(
                "outreach task: unhandled exception campaign=%s recipient=%s: %s",
                campaign_id, recipient_id, exc,
            )
            try:
                recipient = (
                    db.query(OutreachCampaignRecipient)
                    .filter_by(id=recipient_id)
                    .first()
                )
                if recipient is not None and recipient.status not in TERMINAL_STATUSES:
                    recipient.status = "failed"
                    recipient.error = f"task error: {exc}"
                    db.commit()
            except Exception as inner_exc:
                logger.error(
                    "outreach task: failed to mark recipient %s failed: %s",
                    recipient_id, inner_exc,
                )
            return {"status": "error", "error": str(exc)}


def _process_recipient(
    db, campaign_id: int, recipient_id: int
) -> dict:
    """Orchestrate one send: load → guard → send → map → transition campaign."""
    recipient = (
        db.query(OutreachCampaignRecipient)
        .filter_by(id=recipient_id)
        .first()
    )
    if recipient is None:
        logger.warning(
            "outreach task: recipient %s not found (campaign %s)",
            recipient_id, campaign_id,
        )
        return {"status": "error", "error": "recipient not found"}

    # Idempotence guard: duplicate dispatch (retry racing a live task) is a
    # no-op — terminal rows are never re-processed or reset.
    if recipient.status in TERMINAL_STATUSES:
        logger.info(
            "outreach task: recipient %s already terminal (%s) — no-op",
            recipient_id, recipient.status,
        )
        return {"status": "skipped", "error": f"already terminal ({recipient.status})"}

    campaign = (
        db.query(OutreachCampaign)
        .filter_by(id=campaign_id)
        .first()
    )
    if campaign is None:
        logger.warning(
            "outreach task: campaign %s not found for recipient %s",
            campaign_id, recipient_id,
        )
        recipient.status = "failed"
        recipient.error = "campaign not found"
        db.commit()
        return {"status": "error", "error": "campaign not found"}

    from src.models import Organization

    org = (
        db.query(Organization)
        .filter_by(id=campaign.organization_id)
        .first()
    )
    product_name = (org.product_name_display if org else None) or "Rereflect"

    result = outreach_sender.send_outreach_email(
        db,
        org_id=campaign.organization_id,
        customer_email=recipient.customer_email,
        subject=campaign.subject,
        body=campaign.body,
        product_name=product_name,
        template_key=None,
    )

    if result.get("ok"):
        recipient.status = "sent"
        recipient.error = None
    elif result.get("status") == "skipped":
        recipient.status = "skipped"
        recipient.error = result.get("reason", "skipped")
    else:
        recipient.status = "failed"
        recipient.error = result.get("reason", "send failed")

    # Campaign transition: defensive queued→in_progress flip (the route
    # normally sets it), then done when no recipient is left pending.
    if campaign.status == "queued":
        campaign.status = "in_progress"

    # The session may be autoflush=False (production get_db_session is) — the
    # pending count must see this recipient's new status, so flush explicitly.
    db.flush()

    pending = (
        db.query(OutreachCampaignRecipient)
        .filter(
            OutreachCampaignRecipient.campaign_id == campaign_id,
            OutreachCampaignRecipient.status.in_(("queued", "in_progress")),
        )
        .count()
    )
    if pending == 0:
        campaign.status = "done"

    db.commit()

    logger.info(
        "outreach task: campaign=%s recipient=%s -> %s (%s)",
        campaign_id, recipient_id, recipient.status, recipient.error,
    )
    return {"status": recipient.status, "error": recipient.error}
