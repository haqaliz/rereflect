"""
SAML SSO configuration model.

One row per organization. idp_x509_cert is the IdP's PUBLIC signing
certificate (PEM) — it is NOT a secret and NOT encrypted (contrast
oidc_config.client_secret, which is Fernet-encrypted). PEM validation and
the returned SHA-256 fingerprint are route-layer concerns; see
src/api/routes/saml_config.py.
"""
import sqlalchemy as sa
from sqlalchemy import (Column, Integer, String, Text, Boolean, DateTime,
                        ForeignKey, Index, UniqueConstraint, JSON)
from datetime import datetime
from .base import Base


class SamlConfig(Base):
    """Org-wide SAML 2.0 IdP connection (entity id, SSO URL, signing cert, domain allowlist). One row per org."""
    __tablename__ = "saml_configs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    idp_entity_id = Column(String(255), nullable=False)
    idp_sso_url = Column(String(512), nullable=False)          # HTTP-Redirect SSO URL; SSRF-gated on save
    idp_x509_cert = Column(Text, nullable=False)               # PUBLIC PEM signing cert — NOT encrypted
    email_attribute = Column(String(255), nullable=True)       # override for the email attr/NameID mapping
    enabled = Column(Boolean, nullable=False, default=False, server_default=sa.false())
    allowed_email_domains = Column(JSON, nullable=True)        # empty/absent = deny-all (same as OIDC)
    button_label = Column(String(255), nullable=False, default="Sign in with SSO", server_default="Sign in with SSO")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_saml_configs_org_id'),
        Index('ix_saml_configs_org_id', 'organization_id'),
    )

    def __repr__(self):
        return f"<SamlConfig(id={self.id}, org={self.organization_id}, enabled={self.enabled})>"
