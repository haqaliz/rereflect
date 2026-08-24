from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String

from .base import Base


class ReportSchedule(Base):
    """Scheduled AI report configuration for an organization."""
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    report_type = Column(String(50), nullable=False)  # executive_summary | customer_health | feature_prioritization | churn_risk
    date_range_days = Column(Integer, nullable=False, default=30)  # 7 | 30 | 90
    cadence = Column(String(20), nullable=False)  # daily | weekly | monthly
    hour_utc = Column(Integer, nullable=False)  # 0-23
    day_of_week = Column(Integer, nullable=True)  # 0-6, required when cadence=weekly
    day_of_month = Column(Integer, nullable=True)  # 1-31, required when cadence=monthly
    recipients = Column(JSON, nullable=False)  # [email,...], deduped, max 20
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime, nullable=True)  # worker-owned

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index('ix_report_schedules_org_enabled', 'organization_id', 'enabled'),
    )

    def __repr__(self):
        return f"<ReportSchedule(id={self.id}, org={self.organization_id}, type='{self.report_type}', cadence='{self.cadence}')>"