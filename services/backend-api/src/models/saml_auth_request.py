"""
SAML replay / InResponseTo store model.

One row per SP-initiated AuthnRequest we issue. The AuthnRequest `ID` is the
primary key; the ACS marks it `consumed_at` exactly once via a conditional
UPDATE, which is what makes the ACS safe against replayed/duplicated
`SAMLResponse` POSTs and unsolicited (unknown-InResponseTo) responses.

State machine (see src/services/saml_replay.py):
    pending  -> row inserted at /saml/login (register_request)
    consumed -> consumed_at set by the conditional UPDATE on first valid use

`expires_at` is issue-time + SAML_REQUEST_TTL_SECONDS; expired-but-unconsumed
rows resolve to EXPIRED at the ACS and are opportunistically cleaned up on the
next register (no Celery beat). idp_x509_cert-style secrets are not involved —
this table holds no secret material.

Timezone-naive `datetime.utcnow` to match oidc_config.py / auth.py.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from .base import Base


class SamlAuthRequest(Base):
    """Issued SP-initiated AuthnRequest id + one-time consume state. One row per login attempt."""
    __tablename__ = "saml_auth_requests"

    request_id = Column(String(255), primary_key=True)  # AuthnRequest ID (_<uuid>); PK => unique
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # created_at + TTL; drives expiry + cleanup
    consumed_at = Column(DateTime, nullable=True)  # set once, at first valid ACS use

    __table_args__ = (
        Index("ix_saml_auth_requests_org_id", "organization_id"),
        Index("ix_saml_auth_requests_expires_at", "expires_at"),
    )

    def __repr__(self):
        return (
            f"<SamlAuthRequest(request_id={self.request_id!r}, org={self.organization_id}, "
            f"consumed={self.consumed_at is not None})>"
        )
