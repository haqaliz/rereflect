from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Index
from datetime import datetime
from .base import Base


class Report(Base):
    """Saved AI-generated report for an organization."""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)

    # Report classification
    report_type = Column(String(50), nullable=False)  # executive_summary | customer_health | feature_prioritization | churn_risk
    date_range_days = Column(Integer, nullable=False)  # 7 | 30 | 90
    title = Column(String(500), nullable=True)

    # Content
    sections = Column(JSON, nullable=True)           # [{heading, narrative, data, chart_type, chart_data}]
    report_metadata = Column("metadata", JSON, nullable=True)  # {total_feedback, date_start, date_end, generated_at, model_used, tokens_used}

    # PDF state
    pdf_generated = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_reports_org_date', 'organization_id', 'created_at'),
        Index('ix_reports_org_type', 'organization_id', 'report_type'),
    )

    def __repr__(self):
        return f"<Report(id={self.id}, org={self.organization_id}, type='{self.report_type}')>"
