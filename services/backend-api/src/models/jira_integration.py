"""
Jira Cloud integration model.

One row per organization. api_token is Fernet-encrypted via encrypt_api_key
(never stored plaintext). Encryption happens in the route layer, not here.
See src/utils/encryption.py.
"""
import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint, JSON
from datetime import datetime
from .base import Base


class JiraIntegration(Base):
    """Org-wide Jira Cloud connection (email + API token, Basic auth). One row per org."""
    __tablename__ = "jira_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    site_url = Column(String(255), nullable=False)  # canonical https://{site}.atlassian.net
    email = Column(String(255), nullable=False)
    api_token = Column(Text, nullable=False)  # Fernet-encrypted via encrypt_api_key (route-layer concern)
    token_hint = Column(String(8), nullable=True)  # last chars of plaintext, e.g. "...abcd"
    account_id = Column(String(255), nullable=True)  # from GET /myself
    display_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    connected_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)
    status_sync_enabled = Column(Boolean, nullable=False, default=False, server_default=sa.false())
    status_mapping = Column(JSON, nullable=True)  # {jira_status_name: rereflect_status}

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_jira_integrations_org_id'),
        Index('ix_jira_integrations_org_id', 'organization_id'),
    )

    def __repr__(self):
        return f"<JiraIntegration(id={self.id}, org={self.organization_id}, site='{self.site_url}', active={self.is_active})>"


class FeedbackJiraIssue(Base):
    """Links feedback items to Jira issues."""
    __tablename__ = "feedback_jira_issues"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="CASCADE"), nullable=False)
    jira_issue_id = Column(String(255), nullable=False)   # Jira internal issue id, e.g. "10001"
    jira_issue_key = Column(String(50), nullable=False)   # e.g. "ENG-142"
    jira_issue_url = Column(Text, nullable=False)
    jira_issue_title = Column(String(500), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    jira_status = Column(String(100), nullable=True)  # raw Jira status name, e.g. "In Progress"
    jira_status_category = Column(String(20), nullable=True)  # Jira statusCategory key: new/indeterminate/done
    last_status_synced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_feedback_jira_issues_org_id', 'organization_id'),
        Index('ix_feedback_jira_issues_feedback_id', 'feedback_id'),
    )

    def __repr__(self):
        return f"<FeedbackJiraIssue(id={self.id}, feedback={self.feedback_id}, issue='{self.jira_issue_key}')>"
