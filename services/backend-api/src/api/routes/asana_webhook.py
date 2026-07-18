"""
Asana inbound real-time webhook receiver
(status-sync-realtime-mapping/asana-webhook aspect).

Generalizes Jira's receiver (routes/jira_webhook.py) but Asana's protocol
differs in one fundamental way — it requires a HANDSHAKE:

Confirmed external facts (Asana docs):
  - The FIRST POST Asana sends to a newly-registered webhook's target URL
    carries an `X-Hook-Secret` header (and typically an empty body). The
    receiver MUST persist that value and echo the SAME value back in the
    response's `X-Hook-Secret` header with HTTP 200 — if this is not done
    exactly, Asana never activates the webhook. This branch must stay
    I/O-free/fast (<~10s) — no reconcile work happens here.
  - Every SUBSEQUENT event delivery instead carries `X-Hook-Signature` =
    hex HMAC-SHA256(stored_secret, RAW request body) (no prefix, unlike
    Jira's `sha256=` prefix) — verified over the raw bytes, using
    `hmac.compare_digest` (timing-safe).
  - Event payloads are compact change records:
    `{"events": [{"resource": {"gid": ..., "resource_type": "task"},
    "action": "changed", "change": {"field": "completed",
    "new_value": true|false}, ...}]}`. Completion state is read directly
    from `change.new_value` when present (avoids a network round-trip);
    otherwise this falls back to `AsanaClient.get_task(gid)` (mirrors the
    poller's per-task fetch).

Org resolution (WHY a path param, unlike Jira/Linear's per-org
secret-matching loop): Jira/Linear can loop over every active integration's
webhook_secret and see which one verifies the signature — but that ONLY
works once a secret already exists. Asana's very FIRST delivery (the
handshake) carries no signature at all, so there is nothing to match
against yet. Instead, POST /api/v1/integrations/asana/webhook/enable
(Phase 2) registers the webhook's `target` as
`{BACKEND_URL}/api/v1/webhooks/asana/inbound/{integration.id}` — the
integration id is already known BEFORE the webhook (and its secret) exist,
so both the handshake and every later event delivery resolve the org via
this URL path segment. This is FAIL-CLOSED by construction: an unknown/
inactive integration_id, or one with no stored secret yet, always 401s on
the event branch (never a write).

Flow:
  1. Resolve the integration by path `integration_id` (no such row, or an
     inactive one -> 404 is NOT used here -- Asana has no way to react to a
     404 differently than any other failure, so this mirrors Jira/Zendesk's
     "no match -> 401" fail-closed posture uniformly).
  2. HANDSHAKE branch: if the `X-Hook-Secret` header is present, this is
     ALWAYS treated as a (re-)handshake -- store it (Fernet-encrypted,
     overwriting any previous value -- idempotent, mirrors Asana
     re-establishing the webhook) and echo the identical plaintext value
     back via the response `X-Hook-Secret` header, 200, and return
     immediately (no reconcile, no other I/O). R6 fail-closed: if
     LLM_ENCRYPTION_KEY is unset, the secret cannot be safely persisted --
     401, and the header is NOT echoed (never accept a handshake we can't
     actually protect afterward).
  3. EVENT branch (no `X-Hook-Secret` header): verify `X-Hook-Signature`
     against the integration's stored (decrypted) webhook_secret. Missing/
     invalid signature, or no stored secret at all (handshake never
     completed) -> 401.
  4. Parse JSON (400 on invalid/non-dict JSON). Gate on
     `integration.status_sync_enabled` (mirrors the poller -- the webhook
     must never move a status the poller itself wouldn't move) -- 200 no-op
     if disabled.
  5. For each event whose `resource.resource_type == "task"`, resolve
     `completed` from `change.new_value` (when `change.field == "completed"`)
     or fall back to `AsanaClient.get_task(gid)`. Tasks are de-duplicated
     (a single delivery may reference the same task more than once).
  6. Reconcile each unique task via
     `asana_status_reconcile.reconcile_task` (shared `status_sync_core`
     mapping + race-safe apply), commit, return
     `{"status": "ok", "reconcile": [...]}`.
"""
import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.asana_integration import AsanaIntegration
from src.services.asana_client import AsanaAuthError, AsanaClient, AsanaNotFoundError, AsanaTransientError
from src.services.asana_status_reconcile import reconcile_task
from src.utils.encryption import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/asana", tags=["asana-webhooks"])

HOOK_SECRET_HEADER = "X-Hook-Secret"
HOOK_SIGNATURE_HEADER = "X-Hook-Signature"


def _verify_asana_signature(body: bytes, signature_header: str, secret: Optional[str]) -> bool:
    """
    Verify an Asana `X-Hook-Signature` header: hex HMAC-SHA256(secret,
    raw_body) -- NO prefix (unlike Jira's `sha256=`), verified over the raw
    request body.

    Fails closed: a missing/empty secret or missing/empty signature header
    both return False.
    """
    if not secret or not signature_header:
        return False

    expected_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hex, signature_header)


def _ignore(reason: str) -> dict:
    return {"status": "ignored", "reason": reason}


def _resolve_completed(event: dict, client_factory) -> Optional[bool]:
    """
    Resolve a task event's `completed` bool without a network round-trip
    when possible (the `change.new_value` is present on a `completed`
    field-change event); otherwise falls back to `client_factory()`
    (a zero-arg callable returning `(completed, exc)` via
    `AsanaClient.get_task`).

    Returns None when completion state cannot be determined (an
    unresolvable/deleted task, or an event shape carrying neither) --
    callers must skip such tasks (200 no-op), never treat None as False.
    """
    change = event.get("change") or {}
    if change.get("field") == "completed" and "new_value" in change:
        value = change.get("new_value")
        if isinstance(value, bool):
            return value

    return client_factory()


@router.post("/inbound/{integration_id}")
async def asana_webhook_inbound(
    integration_id: int, request: Request, response: Response, db: Session = Depends(get_db)
):
    """
    Receive Asana webhook deliveries (handshake + events) and reconcile
    task completion changes onto linked feedback items in real time
    (fallback: the 15-min poll).
    """
    integration = (
        db.query(AsanaIntegration)
        .filter(
            AsanaIntegration.id == integration_id,
            AsanaIntegration.is_active.is_(True),
        )
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown webhook.")

    hook_secret = request.headers.get(HOOK_SECRET_HEADER)
    if hook_secret:
        # Handshake branch -- ALWAYS wins over any signature check on this
        # request (Asana never sends both headers on the same delivery).
        # I/O-free: persist + echo, no reconcile, no other work.
        try:
            encrypted_secret = encrypt_api_key(hook_secret)
        except ValueError:
            logger.error(
                "asana_webhook: LLM_ENCRYPTION_KEY unset -- cannot persist "
                "handshake secret for integration_id=%s",
                integration_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cannot complete handshake: encryption is not configured.",
            )

        integration.webhook_secret = encrypted_secret
        db.commit()

        response.headers[HOOK_SECRET_HEADER] = hook_secret
        logger.info("asana_webhook: handshake completed for integration_id=%s", integration_id)
        return {"status": "handshake_ok"}

    body = await request.body()
    signature = request.headers.get(HOOK_SIGNATURE_HEADER, "")

    if not signature or not integration.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or unconfigured X-Hook-Signature.",
        )

    try:
        secret = decrypt_api_key(integration.webhook_secret)
    except Exception:
        logger.error(
            "asana_webhook: failed to decrypt webhook_secret for integration_id=%s",
            integration_id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")

    if not _verify_asana_signature(body, signature, secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return _ignore("no_events")

    if not integration.status_sync_enabled:
        logger.info(
            "asana_webhook: status_sync_enabled=false for org %s, ignoring",
            integration.organization_id,
        )
        return _ignore("status_sync_disabled")

    # De-duplicate by task gid -- a single delivery may reference the same
    # task more than once (e.g. multiple field changes in one batch).
    task_events: dict = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        resource = event.get("resource") or {}
        if resource.get("resource_type") != "task":
            continue
        gid = resource.get("gid")
        if not gid:
            continue
        task_events.setdefault(str(gid), event)

    if not task_events:
        return _ignore("no_task_events")

    asana_client: Optional[AsanaClient] = None

    def _fetch_completed(task_gid: str):
        nonlocal asana_client
        if asana_client is None:
            plain_token = decrypt_api_key(integration.api_token)
            asana_client = AsanaClient(plain_token)
        try:
            task = asana_client.get_task(task_gid)
        except (AsanaNotFoundError, AsanaAuthError, AsanaTransientError) as exc:
            logger.warning(
                "asana_webhook: could not fetch task %s for org %s: %s",
                task_gid,
                integration.organization_id,
                exc,
            )
            return None
        if task is None:
            return None
        return bool(task.get("completed"))

    results = []
    try:
        for task_gid, event in task_events.items():
            completed = _resolve_completed(event, lambda gid=task_gid: _fetch_completed(gid))
            if completed is None:
                results.append({"task_gid": task_gid, "action": "unresolved"})
                continue
            result = reconcile_task(db, integration, task_gid, completed)
            results.append({"task_gid": task_gid, **result})
    finally:
        if asana_client is not None:
            asana_client.close()

    db.commit()

    logger.info(
        "asana_webhook: org %s -> reconcile=%s",
        integration.organization_id,
        results,
    )
    return {"status": "ok", "reconcile": results}
