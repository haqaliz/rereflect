"""
Copilot suggested-actions execute route (copilot-suggested-actions,
action-registry aspect; PRD M4/M5/M6/M7/M9).

`POST /api/v1/copilot/actions/execute` takes the message a proposal came from,
the `proposal_id`, the `action` id, and the user-supplied params, then:

1. loads the `Conversation` org-scoped (404 on a foreign/missing id),
2. finds the frozen proposal inside a message's `structured_data` actions item
   (404 when the proposal_id or the requested action is not offered),
3. validates the action against the registry (404 unknown) and enforces the
   entry's `min_role` at execute time (403) — deliberately NO route-level role
   dependency; RBAC is the registry's (PRD M5),
4. validates the user-supplied params against the entry's schema (422),
5. one-shot guard (PRD M9/OQ2): keyed on `proposal_id` alone, never the WS wire
   message_id; a prior successful execution returns the stored outcome without
   re-running and without a second audit row,
6. executes through the registry entry (the cohort is the proposal's frozen
   emails — never the client) and writes exactly one `AuditLog` row.

The one-shot guard reads `AuditLog.details["proposal_id"]`. SQLAlchemy's
JSON-subscript filter is not portable to the SQLite test DB (`.astext` is
unavailable on subscript results and the rendered `JSON_QUOTE(JSON_EXTRACT(...))`
never compares equal), so the guard scopes the query by the plain columns
(org + action + target_type) and filters `details` in Python — low volume,
acceptable per the aspect spec.
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.audit_log import AuditLog
from src.models.conversation import Conversation
from src.models.conversation_message import ConversationMessage
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org
from src.schemas.cohort import BulkActionSummary
from src.services.audit_service import log_action
from src.services.copilot.action_registry import (
    COPILOT_ACTION_AUDIT_ACTION,
    InsufficientRoleError,
    UnknownActionError,
    get_entry,
    require_role,
)

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot-actions"])


class ExecuteActionRequest(BaseModel):
    conversation_id: int
    proposal_id: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)


def _find_frozen_proposal(
    conversation: Conversation, proposal_id: str, action: str
) -> Tuple[Optional[ConversationMessage], Optional[List[str]]]:
    """Locate the proposal inside the conversation's messages.

    Returns `(message, frozen_emails)` for the first message whose
    `structured_data` carries an `actions` item whose `data.proposal_id`
    matches AND whose `data.actions[]` offers the requested `action`. The
    frozen emails come only from that item's params — never from the client.
    """
    for message in conversation.messages:
        raw = message.structured_data
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        for item in items:
            if not isinstance(item, dict) or item.get("data_type") != "actions":
                continue
            data = item.get("data") or {}
            if data.get("proposal_id") != proposal_id:
                continue
            for offered in data.get("actions") or []:
                if isinstance(offered, dict) and offered.get("action") == action:
                    params = offered.get("params") or {}
                    emails = params.get("emails")
                    return message, list(emails) if isinstance(emails, list) else []
    return None, None


def _prior_execution_outcome(
    db: Session, org_id: int, proposal_id: str
) -> Optional[dict]:
    """Return the stored outcome of a prior execution of this proposal_id, if
    any. One-shot guard keyed on proposal_id alone (PRD OQ2): a second attempt
    returns the prior outcome rather than re-executing.

    Only rows carrying an `outcome` in details count as prior executions.
    The JSON key filter happens in Python (see module docstring for why the
    SQL-side subscript filter is not used); candidate rows are scoped down by
    the plain org/action/target_type columns first.
    """
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.organization_id == org_id,
            AuditLog.action == COPILOT_ACTION_AUDIT_ACTION,
            AuditLog.target_type == "copilot_action",
        )
        .order_by(AuditLog.id.desc())
        .all()
    )
    for row in rows:
        details = row.details
        if not isinstance(details, dict):
            continue
        if details.get("proposal_id") != proposal_id:
            continue
        outcome = details.get("outcome")
        if isinstance(outcome, dict):
            return outcome
    return None


@router.post("/actions/execute", response_model=BulkActionSummary)
def execute_copilot_action(
    body: ExecuteActionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
) -> BulkActionSummary:
    """Execute a copilot-suggested action. Registry-gated, org-scoped,
    one-shot, audited."""
    # 1. Conversation must belong to the caller's org.
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == body.conversation_id,
            Conversation.organization_id == current_org.id,
        )
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    # 2. The proposal must exist in that conversation and offer this action.
    proposal_message, frozen_emails = _find_frozen_proposal(
        conversation, body.proposal_id, body.action
    )
    if proposal_message is None:
        raise HTTPException(status_code=404, detail="proposal not found")

    # 3. Registry: only whitelisted actions can run; unknown ids are rejected.
    try:
        entry = get_entry(body.action)
    except UnknownActionError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 4. min_role is enforced HERE, at execute time (PRD M5) — the route itself
    #    deliberately carries no role dependency.
    try:
        require_role(entry, current_user)
    except InsufficientRoleError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # 5. Validate the user-supplied params against the entry's schema.
    try:
        tag: str = entry.params_validator(body.params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 6. One-shot guard — return the stored outcome instead of re-executing.
    prior = _prior_execution_outcome(db, current_org.id, body.proposal_id)
    if prior is not None:
        return BulkActionSummary(**prior)

    # 7. Execute through the registry entry (frozen cohort, add-mode tag).
    result = entry.executor(db, current_org, emails=frozen_emails, tag=tag)
    db.commit()

    # 8. Audit AFTER the executor commit (log_action self-commits) so a failed
    #    executor never leaves an audit row claiming success.
    log_action(
        db,
        org_id=current_org.id,
        user_id=current_user.id,
        user_email=current_user.email,
        action=COPILOT_ACTION_AUDIT_ACTION,
        target_type="copilot_action",
        target_id=proposal_message.id,
        details={
            "proposal_id": body.proposal_id,
            "action": body.action,
            "tag": tag,
            "outcome": result.model_dump(),
        },
        request=request,
    )
    return result
