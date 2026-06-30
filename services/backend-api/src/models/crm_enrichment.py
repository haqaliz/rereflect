"""
CRM enrichment model — per-customer HubSpot data store.

One row per (organization_id, customer_email). Written by the hubspot-sync
worker task and read by the crm-health-component and crm-profile-and-timeline
aspects.

R4 note: keep columns in sync with the worker mirror at
services/worker-service/src/models/__init__.py (CrmEnrichment class).
No shared package enforces consistency — a test asserts column parity.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from .base import Base


class CrmEnrichment(Base):
    """Per-customer HubSpot CRM enrichment snapshot."""

    __tablename__ = "crm_enrichment"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    customer_email = Column(String(255), nullable=False)

    # Company info
    company_name = Column(String(255), nullable=True)
    lifecycle_stage = Column(String(100), nullable=True)
    arr = Column(Float, nullable=True)

    # Renewal proxy — highest-amount open deal with a closedate
    renewal_date = Column(DateTime, nullable=True)
    deal_name = Column(String(255), nullable=True)
    deal_stage = Column(String(100), nullable=True)
    deal_amount = Column(Float, nullable=True)

    # HubSpot object IDs
    hubspot_contact_id = Column(String(100), nullable=True)
    hubspot_company_id = Column(String(100), nullable=True)
    hubspot_deal_id = Column(String(100), nullable=True)

    last_synced_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            name="uq_crm_enrichment_org_email",
        ),
        Index("ix_crm_enrichment_org", "organization_id"),
        Index("ix_crm_enrichment_org_email", "organization_id", "customer_email"),
    )

    def __repr__(self) -> str:
        return (
            f"<CrmEnrichment(id={self.id}, "
            f"org={self.organization_id}, "
            f"email='{self.customer_email}', "
            f"company='{self.company_name}')>"
        )
