"""
Outreach routes (outreach-core aspect).

Read-only template registry for all roles, plus the public tokenized
unsubscribe endpoint. The bulk campaign + playbook send paths consume the
registry and the sender helper; they are their own aspects.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.models.user import User
from src.services.outreach_templates import OUTREACH_TEMPLATES
from src.services.outreach_tokens import verify_unsubscribe_token

router = APIRouter(prefix="/api/v1/outreach", tags=["outreach"])


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
