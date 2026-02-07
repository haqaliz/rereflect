from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class SentimentAnomaly(Base):
    __tablename__ = "sentiment_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    anomaly_type = Column(String(50), nullable=False)  # negative_spike, positive_drop
    severity = Column(String(20), nullable=False)  # warning, critical

    baseline_negative_pct = Column(Float, nullable=False)
    current_negative_pct = Column(Float, nullable=False)
    deviation_pct = Column(Float, nullable=False)

    time_window_hours = Column(Integer, nullable=False, default=24)
    feedback_count = Column(Integer, nullable=False, default=0)

    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_anomaly_org_resolved', 'organization_id', 'is_resolved'),
        Index('ix_anomaly_detected', 'detected_at'),
    )

    def __repr__(self):
        return f"<SentimentAnomaly(id={self.id}, org={self.organization_id}, type='{self.anomaly_type}', severity='{self.severity}')>"
