"""
Outreach routes (outreach-core + bulk-campaign-api aspects).

Read-only template registry for all roles, the public tokenized unsubscribe
endpoint, the org-scoped campaign list (admin/owner) and the queued-recipient
retry endpoint (admin/owner).
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
)
from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.outreach_campaign import (
    OutreachCampaign,
    OutreachCampaignRecipient,
)
from src.models.user import User
from src.services.outreach_templates import OUTREACH_TEMPLATES
from src.services.outreach_tokens import verify_unsubscribe_token

router = APIRouter(prefix="/api/v1/outreach", tags=["outreach"])


# ---------------------------------------------------------------------------
# Campaign list + retry schemas (bulk-campaign-api aspect)
# ---------------------------------------------------------------------------


class CampaignRecipientCounts(BaseModel):
    queued: int
    sent: int
    skipped: int
    failed: int


class CampaignSummary(BaseModel):
    id: int
    subject: str
    status: str  # queued|in_progress|done|failed
    recipient_count: int
    counts: CampaignRecipientCounts
    created_at: datetime


class CampaignListResponse(BaseModel):
    items: List[CampaignSummary]
    total: int
    page: int
    page_size: int


@router.get(
    "/campaigns",
    response_model=CampaignListResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List this org's outreach campaigns, newest first, with per-status
    recipient counts (one GROUP BY — no N+1). Admin/owner only."""
    base = db.query(OutreachCampaign).filter(
        OutreachCampaign.organization_id == current_org.id
    )
    total = base.count()

    campaigns = (
        base.order_by(
            OutreachCampaign.created_at.desc(),
            OutreachCampaign.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    counts_by_campaign = {c.id: {"queued": 0, "sent": 0, "skipped": 0, "failed": 0} for c in campaigns}
    if campaigns:
        rows = (
            db.query(
                OutreachCampaignRecipient.campaign_id,
                OutreachCampaignRecipient.status,
                func.count().label("n"),
            )
            .filter(
                OutreachCampaignRecipient.campaign_id.in_([c.id for c in campaigns])
            )
            .group_by(
                OutreachCampaignRecipient.campaign_id,
                OutreachCampaignRecipient.status,
            )
            .all()
        )
        for campaign_id, stat, n in rows:
            if stat in counts_by_campaign[campaign_id]:
                counts_by_campaign[campaign_id][stat] = n

    return CampaignListResponse(
        items=[
            CampaignSummary(
                id=c.id,
                subject=c.subject,
                status=c.status,
                recipient_count=c.recipient_count,
                counts=CampaignRecipientCounts(**counts_by_campaign[c.id]),
                created_at=c.created_at,
            )
            for c in campaigns
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/campaigns/{campaign_id}/retry",
    dependencies=[Depends(require_admin_or_owner)],
)
def retry_campaign(
    campaign_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Dead-worker recovery: re-enqueue this campaign's `queued` recipients.

    Org-scoped 404 first. Only `queued` rows are re-enqueued — terminal rows
    are immutable (the audit trail is the product of record). No-op 200 zeros
    when nothing is queued. Response is the same BulkOutreachResponse shape
    as the original run: `{matched: queued-found, queued: dispatched,
    skipped: 0, errors}`.
    """
    from src.api.routes.customers import (
        BulkOutreachResponse,
        _dispatch_outreach_tasks,
    )

    campaign = (
        db.query(OutreachCampaign)
        .filter(
            OutreachCampaign.id == campaign_id,
            OutreachCampaign.organization_id == current_org.id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    queued = (
        db.query(OutreachCampaignRecipient)
        .filter(
            OutreachCampaignRecipient.campaign_id == campaign_id,
            OutreachCampaignRecipient.status == "queued",
        )
        .all()
    )

    if not queued:
        return BulkOutreachResponse(matched=0, queued=0, skipped=0, errors=[])

    errors = _dispatch_outreach_tasks(campaign_id, queued)
    dispatched = len(queued) - len(errors)

    if campaign.status == "queued" and dispatched > 0:
        campaign.status = "in_progress"
        db.commit()

    return BulkOutreachResponse(
        matched=len(queued),
        queued=dispatched,
        skipped=0,
        errors=errors,
    )


@router.get("/templates")
def list_outreach_templates(
    current_user: User = Depends(get_current_user),
):
    """List built-in outreach templates (any authed role; read-only)."""
    return [
        {
            "key": tpl.key,
            "label": tpl.label,
            "description": tpl.description,
            "subject": tpl.subject,
            "body": tpl.body,
        }
        for tpl in OUTREACH_TEMPLATES.values()
    ]


@router.get("/unsubscribe")
def unsubscribe(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Public, auth-free unsubscribe: verify the token, flip the customer's
    outreach opt-out flag (upserting a health row when the email has none),
    and render a minimal confirmation page.

    The token is self-describing ('<org_id>:<email>:<digest>'), so org + email
    are recovered from the token itself — a token minted for another org/email
    (or a tampered one) fails verification and returns 400.
    """
    org_part, sep, email_and_digest = token.partition(":")
    if not sep:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid unsubscribe token",
        )
    email, sep2, digest = email_and_digest.rpartition(":")
    if not sep2 or not org_part.isdigit() or not email or not digest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid unsubscribe token",
        )
    token_org_id = int(org_part)

    # The token binds an org: it may only touch a health row of that org.
    # Look the email up first; the verification target is the ROW's org when
    # the row exists (cross-org token -> 400, row untouched) and the token's
    # own org when the email has no row yet (upsert).
    health = (
        db.query(CustomerHealth)
        .filter(CustomerHealth.customer_email == email)
        .order_by(CustomerHealth.organization_id)
        .first()
    )

    if health is not None:
        if not verify_unsubscribe_token(token, health.organization_id, email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid unsubscribe token",
            )
    else:
        if not verify_unsubscribe_token(token, token_org_id, email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid unsubscribe token",
            )
        health = CustomerHealth(
            organization_id=token_org_id,
            customer_email=email,
        )
        db.add(health)

    health.outreach_opt_out = True
    db.commit()

    return HTMLResponse(
        "<!DOCTYPE html><html><head><title>Unsubscribed</title></head>"
        f"<body><h1>You're unsubscribed</h1>"
        f"<p>{email} will no longer receive outreach emails from this "
        f"organization.</p></body></html>"
    )
