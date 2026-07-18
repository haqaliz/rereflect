"""
Jira Cloud inbound real-time webhook receiver
(status-sync-realtime-mapping/jira-webhook aspect).

Generalizes Zendesk's receiver (source_webhooks.py::handle_zendesk_webhook,
fail-closed) and Linear's per-org secret-matching
(routes/linear_webhook.py::_find_integration_by_secret). Unlike Linear,
this is FAIL-CLOSED on a missing/empty secret (Zendesk's posture) --
Linear's `return True` on an empty secret is a known anti-pattern, not
mirrored here.

Confirmed external fact (Jira Cloud docs): a webhook registered WITH a
secret signs the raw request body and sends
`X-Hub-Signature: sha256=<hex HMAC-SHA256(secret, raw_body)>` (UTF-8).
Verified over the RAW bytes (not the re-serialized/parsed JSON), the
`sha256=` prefix is stripped, and comparison uses `hmac.compare_digest`
(timing-safe).

Flow:
  1. Read the raw body FIRST (both signature verification and JSON parsing
     must operate on the exact same bytes Jira sent).
  2. Resolve the org by trying each active JiraIntegration that has a
     webhook_secret and checking the signature against it (Linear-style
     `_find_integration_by_secret`) -- we generate distinct per-org secrets,
     so exactly one integration (if any) will verify. Missing/invalid
     signature, or no integration's secret matches -> 401.
  3. Parse JSON (400 on invalid/non-dict JSON).
  4. Discriminate the event: only `webhookEvent == "jira:issue_updated"`
     with a `status` field changelog item is handled; everything else is a
     200 no-op (never a write). This mirrors Zendesk's anti-spoof
     discriminator pattern -- a status-change delivery can never be
     confused with any other Jira webhook event shape.
  5. Gate on `integration.status_sync_enabled` (mirrors the poller -- the
     webhook must never move a status the poller itself wouldn't move).
  6. Extract issue id/key + new status name + Jira `statusCategory` key,
     reconcile via `jira_status_reconcile.reconcile_issue` (shared
     `status_sync_core` mapping + race-safe apply -- see that module's
     docstring), commit, and return `{"status": "ok", "reconcile": ...}`.
"""
import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.jira_integration import JiraIntegration
from src.services.jira_status_reconcile import reconcile_issue
from src.utils.encryption import decrypt_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/jira", tags=["jira-webhooks"])

_SIGNATURE_PREFIX = "sha256="


def _verify_jira_signature(body: bytes, signature_header: str, secret: Optional[str]) -> bool:
    """
    Verify a Jira Cloud webhook `X-Hub-Signature` header:
    `sha256=<hex HMAC-SHA256(secret, raw_body)>`, verified over the raw
    request body.

    Fails closed: a missing/empty secret, missing/empty signature header, or
    a header without the `sha256=` prefix all return False.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith(_SIGNATURE_PREFIX):
        return False

    provided_hex = signature_header[len(_SIGNATURE_PREFIX):]
    expected_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hex, provided_hex)


def _find_integration_by_secret(
    signature_header: str, body: bytes, db: Session
) -> Optional[JiraIntegration]:
    """
    Find the active JiraIntegration whose (decrypted) webhook_secret matches
    the given signature. We generate distinct per-org secrets, so this
    checks every active, webhook-enabled integration (Linear-style) rather
    than resolving the org from the payload first -- the payload carries no
    reliable org identifier of its own.

    A corrupt/undecryptable stored secret is treated as no-match (never a
    500) -- the loop simply continues to the next integration.
    """
    candidates = (
        db.query(JiraIntegration)
        .filter(
            JiraIntegration.is_active.is_(True),
            JiraIntegration.webhook_secret.isnot(None),
        )
        .all()
    )
    for integration in candidates:
        try:
            secret = decrypt_api_key(integration.webhook_secret)
        except Exception:
            logger.error(
                "jira_webhook: failed to decrypt webhook_secret for integration_id=%s",
                integration.id,
            )
            continue
        if _verify_jira_signature(body, signature_header, secret):
            return integration
    return None


def _ignore(reason: str) -> dict:
    return {"status": "ignored", "reason": reason}


def _extract_status_changelog_item(payload: dict) -> Optional[dict]:
    changelog = payload.get("changelog") or {}
    items = changelog.get("items") or []
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("field") == "status":
            return item
    return None


@router.post("/inbound")
async def jira_webhook_inbound(request: Request, db: Session = Depends(get_db)):
    """
    Receive Jira Cloud webhook events and reconcile issue status changes
    onto linked feedback items in real time (fallback: the 15-min poll).
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature", "")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature header.",
        )

    integration = _find_integration_by_secret(signature, body, db)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if payload.get("webhookEvent") != "jira:issue_updated":
        logger.debug("jira_webhook: ignoring webhookEvent=%r", payload.get("webhookEvent"))
        return _ignore("event_not_handled")

    if _extract_status_changelog_item(payload) is None:
        return _ignore("no_status_change")

    if not integration.status_sync_enabled:
        logger.info(
            "jira_webhook: status_sync_enabled=false for org %s, ignoring",
            integration.organization_id,
        )
        return _ignore("status_sync_disabled")

    issue = payload.get("issue") or {}
    issue_id = issue.get("id")
    issue_key = issue.get("key")
    fields = issue.get("fields") or {}
    status_field = fields.get("status") or {}
    status_name = status_field.get("name")
    status_category = (status_field.get("statusCategory") or {}).get("key")

    if issue_id is None or not status_name or not status_category:
        logger.warning(
            "jira_webhook: missing issue id/status/category for org %s",
            integration.organization_id,
        )
        return _ignore("missing_issue_status_fields")

    result = reconcile_issue(db, integration, issue_id, issue_key, status_name, status_category)
    db.commit()

    logger.info(
        "jira_webhook: issue %s org %s -> reconcile=%s",
        issue_key or issue_id,
        integration.organization_id,
        result,
    )
    return {"status": "ok", "reconcile": result}
