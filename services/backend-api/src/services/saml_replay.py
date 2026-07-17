"""
SAML replay / InResponseTo store — the explicit pending -> consumed state
machine over `saml_auth_requests` that makes the ACS safe.

Route-free by design (mirrors saml_provider.py): session-in / enum-out, no
FastAPI imports. The next aspect's `/saml/login` route calls
`register_request` after building the AuthnRequest; the `/saml/callback` (ACS)
route calls `consume_request` before trusting a validated assertion.

The exactly-once guarantee is a single race-safe conditional statement:

    UPDATE saml_auth_requests
       SET consumed_at = :now
     WHERE request_id = :rid AND consumed_at IS NULL AND expires_at >= :now

Only the first caller flips `consumed_at`; a duplicate/polled ACS POST re-runs
the UPDATE, matches 0 rows, and disambiguates to REPLAY. A missing row is
UNSOLICITED (SP-initiated only in slice 1 — every legitimate response carries
an InResponseTo we issued); an unconsumed-but-past-expiry row is EXPIRED.

`_now()` returns naive UTC `datetime` (matching the model / the rest of the
codebase) and is the single monkeypatch surface for expiry tests. NOTE the
unit difference from `saml_provider._now()` (epoch seconds) — kept as two
clearly-named shims on purpose to avoid unit confusion.
"""
import logging
import os
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import update

from src.models.saml_auth_request import SamlAuthRequest

logger = logging.getLogger(__name__)

# Request-id row lifetime / unsolicited-after-expiry window. Matches the OIDC
# STATE_TTL_SECONDS=600 default.
SAML_REQUEST_TTL_SECONDS = int(os.getenv("SAML_REQUEST_TTL_SECONDS", "600"))

# Upper bound on rows deleted per opportunistic cleanup pass so a single
# register never turns into an unbounded DELETE.
_CLEANUP_MAX_ROWS = 500


class ConsumeOutcome(str, Enum):
    """Result of an ACS consume attempt. The route maps each to a ?sso_error=."""
    OK = "ok"
    REPLAY = "replay"
    UNSOLICITED = "unsolicited"
    EXPIRED = "expired"


def _now() -> datetime:
    """Naive UTC wall clock. A thin wrapper so expiry tests can monkeypatch it."""
    return datetime.utcnow()


def _cleanup_expired(db, *, limit: int = _CLEANUP_MAX_ROWS) -> None:
    """Best-effort, bounded delete of expired rows. A failure here must NEVER
    block a login, so it is caught and logged (the caller proceeds regardless).

    Bounded via an explicit id-select + IN-delete rather than `DELETE ... LIMIT`
    so it is portable across SQLite (tests) and PostgreSQL (prod)."""
    try:
        now = _now()
        stale_ids = [
            row[0]
            for row in (
                db.query(SamlAuthRequest.request_id)
                .filter(SamlAuthRequest.expires_at < now)
                .limit(limit)
                .all()
            )
        ]
        if stale_ids:
            db.query(SamlAuthRequest).filter(
                SamlAuthRequest.request_id.in_(stale_ids)
            ).delete(synchronize_session=False)
            db.commit()
    except Exception:  # noqa: BLE001 - cleanup is best-effort by contract
        db.rollback()
        logger.warning("SAML replay-store expired-row cleanup failed", exc_info=True)


def register_request(
    db,
    *,
    request_id: str,
    organization_id: int,
    ttl_seconds: int = SAML_REQUEST_TTL_SECONDS,
) -> None:
    """Persist a freshly-issued AuthnRequest id as `pending`. Opportunistically
    cleans up expired rows first (bounded, best-effort)."""
    _cleanup_expired(db)
    now = _now()
    db.add(
        SamlAuthRequest(
            request_id=request_id,
            organization_id=organization_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    db.commit()


def consume_request(db, *, request_id: str) -> ConsumeOutcome:
    """Attempt a one-time consume of an issued AuthnRequest id.

    Returns OK exactly once for a valid, unconsumed, unexpired row; REPLAY on
    any subsequent attempt; UNSOLICITED if no such row was ever issued; EXPIRED
    if the row is still pending but past its TTL.
    """
    now = _now()
    result = db.execute(
        update(SamlAuthRequest)
        .where(
            SamlAuthRequest.request_id == request_id,
            SamlAuthRequest.consumed_at.is_(None),
            SamlAuthRequest.expires_at >= now,
        )
        .values(consumed_at=now)
    )
    db.commit()

    if result.rowcount == 1:
        return ConsumeOutcome.OK

    # The UPDATE matched nothing — disambiguate why.
    row = db.query(SamlAuthRequest).filter_by(request_id=request_id).first()
    if row is None:
        return ConsumeOutcome.UNSOLICITED
    if row.consumed_at is not None:
        return ConsumeOutcome.REPLAY
    if row.expires_at < now:
        return ConsumeOutcome.EXPIRED
    return ConsumeOutcome.UNSOLICITED  # defensive fallthrough
