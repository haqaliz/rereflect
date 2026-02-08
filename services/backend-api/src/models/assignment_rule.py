from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class AssignmentRule(Base):
    """Category-based auto-assignment rule for an organization."""
    __tablename__ = "assignment_rules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    rule_type = Column(String(50), nullable=False, default="category")
    match_field = Column(String(100), nullable=False)  # pain_point_category, feature_request_category, urgent_category, source, sentiment_label
    match_value = Column(String(255), nullable=False)
    assign_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    priority = Column(Integer, nullable=False, default=0)  # Higher = checked first
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_assignment_rule_org", "organization_id"),
    )

    def __repr__(self):
        return f"<AssignmentRule(id={self.id}, org={self.organization_id}, field='{self.match_field}', value='{self.match_value}')>"
