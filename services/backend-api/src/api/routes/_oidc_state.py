"""
Stateless `state` signing + PKCE helpers for the OIDC login flow
(`GET /auth/oidc/start` and `GET /auth/oidc/callback`).

Mirrors `salesforce_integration.py`'s `_hash_nonce`/`_sign_state`/`_verify_state`
mechanics (HMAC-SHA256 keyed on the app-wide `JWT_SECRET`, base64url payload,
`hmac.compare_digest` on verify) but is intentionally NOT a copy of those
private functions: OIDC login has no prior session, so the signed payload
here carries ONLY a CSRF nonce hash — never an org_id/user_id. Identity is
resolved later from the validated ID token (see spec.md, "load-bearing
divergence from the Salesforce precedent").
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional, Tuple

STATE_TTL_SECONDS = 600  # 10 minutes


def _app_secret() -> str:
    from src.api.auth import JWT_SECRET
    return JWT_SECRET


def hash_nonce(raw: str) -> str:
    """SHA-256 hex digest of a raw nonce (stored/compared, never the raw value)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def sign_state(nonce_hash: str) -> str:
    """
    Sign a stateless `state` param (HMAC-SHA256, app-secret keyed).

    Payload carries only `nonce_hash` (CSRF binding to the session-nonce
    cookie set by /start) + an issued-at timestamp for TTL — no user/org id.
    """
    payload = {
        "nonce_hash": nonce_hash,
        "ts": int(time.time()),
        "rand": secrets.token_urlsafe(8),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
    sig = hmac.new(_app_secret().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_state(state: str) -> Optional[dict]:
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
    if time.time() - payload.get("ts", 0) > STATE_TTL_SECONDS:
        return None
    return payload


def make_pkce() -> Tuple[str, str]:
    """Generate a PKCE (verifier, challenge) pair. challenge = base64url(sha256(verifier)), no padding."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge
