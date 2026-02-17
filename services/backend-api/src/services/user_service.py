"""Shared user service for cleanup and deletion operations."""
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.notification import Notification
from src.models.user_alert_preference import UserAlertPreference
from src.models.saved_view import SavedView
from src.models.assignment_rule import AssignmentRule
from src.models.dashboard_layout import UserDashboardLayout
from src.models.audit_log import AuditLog
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.feedback_note import FeedbackNote
from src.models.shared_link import SharedLink
from src.models.team_invite import TeamInvite
from src.models.feedback import FeedbackItem


def cleanup_and_delete_user(db: Session, user: User) -> None:
    """Clean up all related records and delete a user.

    Deletes user-owned personal data and nullifies references
    in preserved historical records before deleting the user row.
    """
    user_id = user.id

    # 1. Delete user-owned records (personal data)
    db.query(Notification).filter(Notification.user_id == user_id).delete()
    db.query(UserAlertPreference).filter(UserAlertPreference.user_id == user_id).delete()
    db.query(SavedView).filter(SavedView.created_by_id == user_id).delete()
    db.query(AssignmentRule).filter(AssignmentRule.assign_to_user_id == user_id).delete()
    db.query(UserDashboardLayout).filter(UserDashboardLayout.user_id == user_id).delete()

    # 2. Nullify references in preserved records (history/shared data)
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update({"user_id": None})
    db.query(FeedbackWorkflowEvent).filter(FeedbackWorkflowEvent.actor_id == user_id).update({"actor_id": None})
    db.query(FeedbackNote).filter(FeedbackNote.author_id == user_id).update({"author_id": None})
    db.query(SharedLink).filter(SharedLink.created_by_id == user_id).update({"created_by_id": None})
    db.query(TeamInvite).filter(TeamInvite.invited_by_id == user_id).update({"invited_by_id": None})
    db.query(FeedbackItem).filter(FeedbackItem.assigned_to == user_id).update({"assigned_to": None})
    db.query(User).filter(User.invited_by_id == user_id).update({"invited_by_id": None})

    db.delete(user)
