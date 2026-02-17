from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, UniqueConstraint
from .base import Base


class UserAlertPreference(Base):
    """Per-user alert preferences for each alert type."""
    __tablename__ = "user_alert_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50), nullable=False)  # "urgent_feedback", "sentiment_spike", "churn_risk", "volume_spike"
    is_enabled = Column(Boolean, default=True, nullable=False)
    channel_email = Column(Boolean, default=False, nullable=False)
    channel_slack = Column(Boolean, default=True, nullable=False)
    channel_inapp = Column(Boolean, default=True, nullable=False)
    channel_intercom = Column(Boolean, default=False, nullable=False)
    threshold_value = Column(Float, nullable=True)  # sentiment spike: 50.0 (%), volume spike: 2.0 (multiplier)
    retention_days = Column(Integer, default=30, nullable=False, server_default="30")

    __table_args__ = (
        UniqueConstraint("user_id", "alert_type", name="uq_user_alert_type"),
    )

    def __repr__(self):
        return f"<UserAlertPreference(user={self.user_id}, type='{self.alert_type}', enabled={self.is_enabled})>"
