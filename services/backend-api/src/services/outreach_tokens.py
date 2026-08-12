"""
Unsubscribe token helpers — canonical backend implementation
(outreach-core aspect).

Stateless, signed token over ``'{org_id}:{email}'`` (HMAC-SHA256 keyed by
`LLM_ENCRYPTION_KEY`), hex-encoded digest. Self-describing format
``'{org_id}:{normalized_email}:{hex digest}'`` so the public unsubscribe
endpoint can recover org + email from the token alone and verify the digest
— no token table, no state.

The worker mirrors `make_unsubscribe_token` in
`worker-service/src/services/outreach_sender.py` (the worker composes the
List-Unsubscribe header; only the backend needs `verify`). Both suites pin
the format via an identical reference implementation, so drift fails on the
side that moved.
"""

import hashlib
import hmac
import os
from typing import Tuple


def _key() -> bytes:
    key = os.environ.get("LLM_ENCRYPTION_KEY", "")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY environment variable is not set")
    return key.encode("utf-8")


def _digest(payload: str) -> str:
    return hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_unsubscribe_token(org_id: int, customer_email: str) -> str:
    """Mint an unsubscribe token binding *org_id* + *customer_email*.

    The email is normalized (strip + lowercase) before signing, so a token
    minted for ' Alice@Example.COM ' verifies against 'alice@example.com'.
    """
    email = customer_email.strip().lower()
    payload = f"{org_id}:{email}"
    return f"{payload}:{_digest(payload)}"


def _split_token(token: str) -> Tuple[str, str] | None:
    """Split '<org>:<email>:<digest>' into (payload, digest).

    Emails never contain ':' and the digest is hex, so the last ':' is the
    digest separator. Returns None for malformed tokens.
    """
    sep = token.rfind(":")
    if sep <= 0:
        return None
    return token[:sep], token[sep + 1 :]


def verify_unsubscribe_token(token: str, org_id: int, customer_email: str) -> bool:
    """Return True iff *token* is a valid signature for this org + email.

    Constant-time digest comparison (no early length-exit). A token minted
    for a different org/email, or with a tampered payload or digest, returns
    False.
    """
    email = customer_email.strip().lower()
    expected_payload = f"{org_id}:{email}"
    split = _split_token(token)
    if split is None:
        return False
    payload, digest = split
    if payload != expected_payload:
        return False
    return hmac.compare_digest(digest, _digest(expected_payload))
