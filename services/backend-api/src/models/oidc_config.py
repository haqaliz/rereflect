"""
OIDC SSO configuration model.

One row per organization. client_secret is Fernet-encrypted via
encrypt_api_key (never stored plaintext). secret_hint holds the last chars
of plaintext for display. Encryption happens in the route layer, not here.
See src/utils/encryption.py.
"""
import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint, JSON
from datetime import datetime
from .base import Base


class OidcConfig(Base):
    """Org-wide OIDC SSO connection (issuer, client id/secret, domain allowlist). One row per org."""
    __tablename__ = "oidc_configs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    issuer_url = Column(String(255), nullable=False)  # operator-supplied discovery base; stored, never fetched here
    client_id = Column(String(255), nullable=False)
    client_secret = Column(Text, nullable=False)  # Fernet-encrypted via encrypt_api_key (route-layer concern)
    secret_hint = Column(String(8), nullable=True)  # last chars of plaintext, e.g. "...abcd"
    enabled = Column(Boolean, nullable=False, default=False, server_default=sa.false())
    allowed_email_domains = Column(JSON, nullable=True)  # list of lowercased domain strings; empty/absent = deny-all
    button_label = Column(String(255), nullable=False, default="Sign in with SSO", server_default="Sign in with SSO")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_oidc_configs_org_id'),
        Index('ix_oidc_configs_org_id', 'organization_id'),
    )

    def __repr__(self):
        return f"<OidcConfig(id={self.id}, org={self.organization_id}, enabled={self.enabled})>"
