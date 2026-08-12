"""
Outreach routes (outreach-core aspect).

Read-only template registry for all roles, plus the public unsubscribe
endpoint (added in the unsubscribe phase). The bulk campaign + playbook
send paths consume the registry and the sender helper; they are their own
aspects.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User
from src.services.outreach_templates import OUTREACH_TEMPLATES

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
