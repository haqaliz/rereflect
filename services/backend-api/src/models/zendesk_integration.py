"""
Zendesk integration model.

One row per organization. api_token is Fernet-encrypted via encrypt_api_key
(never stored plaintext). webhook_secret is likewise Fernet-encrypted, but
nullable — it is generated at connect time (secrets.token_urlsafe(32)), not
supplied by the operator. Encryption happens in the route layer, not here.
See src/utils/encryption.py.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from datetime import datetime
from .base import Base


class ZendeskIntegration(Base):
    """Org-wide Zendesk connection (email + API token, Basic auth). One row per org."""
    __tablename__ = "zendesk_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    subdomain = Column(String(255), nullable=False)  # bare subdomain, e.g. "acme" (not a URL)
    email = Column(String(255), nullable=False)
    api_token = Column(Text, nullable=False)  # Fernet-encrypted via encrypt_api_key (route-layer concern)
    token_hint = Column(String(8), nullable=True)  # last chars of plaintext, e.g. "...abcd"
    webhook_secret = Column(Text, nullable=True)  # Fernet-encrypted; generated at connect time
    account_user_id = Column(String(255), nullable=True)  # from GET /users/me.json
    display_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    connected_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_zendesk_integrations_org_id'),
        Index('ix_zendesk_integrations_org_id', 'organization_id'),
    )

    def __repr__(self):
        return f"<ZendeskIntegration(id={self.id}, org={self.organization_id}, subdomain='{self.subdomain}', active={self.is_active})>"
