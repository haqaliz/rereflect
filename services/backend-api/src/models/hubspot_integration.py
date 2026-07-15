"""
HubSpot CRM integration model.

One row per organization. access_token is Fernet-encrypted via encrypt_api_key
(never stored plaintext). See src/utils/encryption.py.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    DateTime, Index, UniqueConstraint, JSON,
)
from datetime import datetime
from .base import Base


class HubSpotIntegration(Base):
    """Org-wide HubSpot private-app token connection. One row per org."""
    __tablename__ = "hubspot_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, nullable=False
    )  # no FK — worker mirror uses same no-FK pattern
    access_token = Column(Text, nullable=False)   # Fernet-encrypted via encrypt_api_key
    token_hint = Column(String(8), nullable=True)  # last 4 chars of plaintext, e.g. "...abcd"
    hub_id = Column(String(64), nullable=True)
    portal_name = Column(String(255), nullable=True)
    arr_property_name = Column(String(255), nullable=False,
                               default="annualrevenue", server_default="annualrevenue")
    connected_by_user_id = Column(Integer, nullable=True)
    connected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)
    contacts_synced = Column(Integer, nullable=False, default=0, server_default="0")
    contacts_matched = Column(Integer, nullable=False, default=0, server_default="0")

    # CRM writeback (writeback-config-api aspect): push health scores back to HubSpot
    writeback_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    writeback_field_name = Column(String(255), nullable=True)
    last_writeback_at = Column(DateTime, nullable=True)
    last_writeback_status = Column(String(50), nullable=True)
    last_writeback_error = Column(Text, nullable=True)
    contacts_written = Column(Integer, nullable=False, default=0, server_default="0")

    # CRM-sourced churn labels (crm-churn-labels aspect): default-deny opt-in
    churn_labels_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    churn_label_config = Column(JSON, nullable=True)  # {"renewal_pipeline_ids": [...]}

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_hubspot_integrations_org_id"),
        Index("ix_hubspot_integrations_org_id", "organization_id"),
    )

    def __repr__(self):
        return (
            f"<HubSpotIntegration(id={self.id}, "
            f"org={self.organization_id}, "
            f"portal='{self.portal_name}', "
            f"active={self.is_active})>"
        )
