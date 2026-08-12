from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from datetime import datetime
from .base import Base


class OutreachCampaign(Base):
    """Bulk outreach campaign audit row (bulk-campaign-api aspect).

    One row per operator-initiated bulk send; the per-recipient outcome rows
    live in `outreach_campaign_recipients`. Status lifecycle:
    queued -> in_progress -> done (or `failed` per campaign-level failures).
    """
    __tablename__ = "outreach_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    recipient_count = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="queued", server_default="queued")
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class OutreachCampaignRecipient(Base):
    """Per-recipient outreach campaign result row.

    Status: queued -> sent | skipped | failed (terminal). `error` carries the
    loud skip/failure reason. Unique per (campaign, email) — a campaign can
    never hold two rows for the same address.
    """
    __tablename__ = "outreach_campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(
        Integer,
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_email = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="queued", server_default="queued")
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "customer_email",
            name="uq_outreach_campaign_recipients_campaign_email",
        ),
    )
