"""
Stateless `state` signing for the OAuth connect flows (Slack, Intercom, Linear).

Mirrors `salesforce_integration.py`'s `_sign_state`/`_verify_state` mechanics
(HMAC-SHA256 keyed on the app-wide `JWT_SECRET`, base64url payload,
`hmac.compare_digest` on verify) so the digest/encoding stays byte-identical
across every OAuth flow. The signed payload carries everything the old
in-process dict carried — `organization_id` (+ `user_id` for Linear) — plus
`name`, a fresh `nonce` and an `exp` timestamp. There is no server-side
store, so a callback that lands on a different replica than the one that
issued the authorize URL still verifies, and nothing unbounded can
accumulate in memory.

Fail-closed contract: any invalid/forged/expired state verifies to `None`.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

STATE_TTL_SECONDS = 600  # 10 minutes


def _app_secret() -> str:
    from src.api.auth import JWT_SECRET
    return JWT_SECRET


def sign_oauth_state(organization_id: int, name: str, user_id: Optional[int] = None) -> str:
    """
    Sign a stateless OAuth `state` param (HMAC-SHA256, app-secret keyed).

    Payload carries `{organization_id, name, nonce, exp}` (plus `user_id`
    when given — Linear records who connected). `exp` bounds replay to
    `STATE_TTL_SECONDS`.
    """
    payload = {
        "organization_id": organization_id,
        "name": name,
        "nonce": secrets.token_urlsafe(8),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    if user_id is not None:
        payload["user_id"] = user_id
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
    sig = hmac.new(_app_secret().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_oauth_state(state: str) -> Optional[dict]:
    """Verify + decode a signed state. Returns the payload dict, or None if invalid/expired."""
    if not state or "." not in state:
        return None
    payload_b64, _, sig = state.rpartition(".")
    expected_sig = hmac.new(_app_secret().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None
    if time.time() > payload.get("exp", 0):
        return None
    return payload
