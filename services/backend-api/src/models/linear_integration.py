from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class LinearIntegration(Base):
    """Org-wide Linear OAuth connection."""
    __tablename__ = "linear_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    access_token = Column(Text, nullable=False)  # Fernet-encrypted OAuth token
    linear_org_id = Column(String(255), nullable=False)
    linear_org_name = Column(String(255), nullable=False)
    connected_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    webhook_secret = Column(String(255), nullable=False)
    webhook_id = Column(String(255), nullable=True)  # Linear webhook UUID for deletion

    # Issue template defaults (used when creating issues from feedback)
    issue_title_template = Column(Text, nullable=True)
    issue_description_template = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_linear_integrations_org_id'),
        Index('ix_linear_integrations_org_id', 'organization_id'),
    )

    def __repr__(self):
        return f"<LinearIntegration(id={self.id}, org={self.organization_id}, linear_org='{self.linear_org_name}', active={self.is_active})>"


class LinearTeamMapping(Base):
    """Maps Rereflect categories to Linear teams."""
    __tablename__ = "linear_team_mappings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    rereflect_category = Column(String(100), nullable=False)  # e.g., "pain_point", "feature_request", "bug"
    linear_team_id = Column(String(255), nullable=False)
    linear_team_name = Column(String(255), nullable=False)
    linear_project_id = Column(String(255), nullable=True)
    linear_project_name = Column(String(255), nullable=True)
    priority = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index('ix_linear_team_mappings_org_category', 'organization_id', 'rereflect_category'),
    )

    def __repr__(self):
        return f"<LinearTeamMapping(id={self.id}, org={self.organization_id}, category='{self.rereflect_category}', team='{self.linear_team_name}')>"


class LinearStatusMapping(Base):
    """Configurable Linear status type → Rereflect status mapping per org."""
    __tablename__ = "linear_status_mappings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    linear_status_name = Column(String(255), nullable=False)  # e.g., "In Progress", "Done"
    linear_status_type = Column(String(50), nullable=False)   # backlog, unstarted, started, completed, canceled
    rereflect_status = Column(String(50), nullable=False)     # new, in_review, resolved, closed

    __table_args__ = (
        Index('ix_linear_status_mappings_org_type', 'organization_id', 'linear_status_type'),
    )

    def __repr__(self):
        return f"<LinearStatusMapping(id={self.id}, org={self.organization_id}, linear_type='{self.linear_status_type}', rereflect='{self.rereflect_status}')>"


class FeedbackLinearIssue(Base):
    """Links feedback items to Linear issues."""
    __tablename__ = "feedback_linear_issues"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="CASCADE"), nullable=False)
    linear_issue_id = Column(String(255), nullable=False)       # Linear issue UUID
    linear_issue_identifier = Column(String(50), nullable=False) # e.g., "ENG-142"
    linear_issue_url = Column(Text, nullable=False)
    linear_issue_title = Column(String(500), nullable=False)
    linear_status = Column(String(255), nullable=True)           # Current Linear status (updated via webhook)
    linear_assignee = Column(String(255), nullable=True)         # Current assignee name
    linear_priority = Column(Integer, nullable=True)             # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_feedback_linear_issues_org_id', 'organization_id'),
        Index('ix_feedback_linear_issues_feedback_id', 'feedback_id'),
        Index('ix_feedback_linear_issues_linear_issue_id', 'linear_issue_id'),
    )

    def __repr__(self):
        return f"<FeedbackLinearIssue(id={self.id}, feedback={self.feedback_id}, issue='{self.linear_issue_identifier}')>"
