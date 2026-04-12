"""GDPR-compliant account management endpoints.

Endpoints
---------
GET  /api/v1/account/export          — Download a ZIP of all personal data
POST /api/v1/account/delete-request  — Request account deletion (deactivates immediately)
POST /api/v1/account/cancel-deletion — Cancel a pending deletion (works for deactivated users)
"""

import csv
import io
import json
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_current_user_allow_deactivated
from src.database.session import get_db
from src.models.conversation import Conversation
from src.models.conversation_message import ConversationMessage
from src.models.feedback import FeedbackItem
from src.models.feedback_note import FeedbackNote
from src.models.report import Report
from src.models.user import User
from src.models.user_alert_preference import UserAlertPreference

router = APIRouter(prefix="/api/v1/account", tags=["account"])


# ---------------------------------------------------------------------------
# Data Export
# ---------------------------------------------------------------------------

@router.get("/export")
def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a ZIP archive containing all personal data for the authenticated user."""

    org = current_user.organization
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

        # ── profile.json ────────────────────────────────────────────────────
        profile = {
            "email": current_user.email,
            "role": current_user.role,
            "org_name": org.name,
            "joined_at": current_user.joined_at.isoformat() if current_user.joined_at else None,
            "plan": org.plan,
        }
        zf.writestr("profile.json", json.dumps(profile, indent=2))

        # ── feedbacks (JSON + CSV) ───────────────────────────────────────────
        feedbacks = (
            db.query(FeedbackItem)
            .filter(FeedbackItem.organization_id == current_user.organization_id)
            .all()
        )

        feedbacks_data = [
            {
                "id": f.id,
                "text": f.text,
                "source": f.source,
                "sentiment_label": f.sentiment_label,
                "sentiment_score": f.sentiment_score,
                "is_urgent": f.is_urgent,
                "tags": f.tags,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in feedbacks
        ]
        zf.writestr("feedbacks.json", json.dumps(feedbacks_data, indent=2))

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["id", "text", "source", "sentiment_label", "sentiment_score", "is_urgent", "created_at"])
        for f in feedbacks:
            writer.writerow([
                f.id,
                f.text,
                f.source,
                f.sentiment_label,
                f.sentiment_score,
                f.is_urgent,
                f.created_at.isoformat() if f.created_at else "",
            ])
        zf.writestr("feedbacks.csv", csv_buf.getvalue())

        # ── conversations + messages ─────────────────────────────────────────
        conversations = (
            db.query(Conversation)
            .filter(
                Conversation.organization_id == current_user.organization_id,
                Conversation.created_by_user_id == current_user.id,
            )
            .all()
        )

        conv_ids = [c.id for c in conversations]
        messages = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id.in_(conv_ids))
            .all()
            if conv_ids
            else []
        )

        msg_by_conv: dict[int, list] = {}
        for m in messages:
            msg_by_conv.setdefault(m.conversation_id, []).append(
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
            )

        conversations_data = [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "messages": msg_by_conv.get(c.id, []),
            }
            for c in conversations
        ]
        zf.writestr("conversations.json", json.dumps(conversations_data, indent=2))

        # ── notes ────────────────────────────────────────────────────────────
        notes = (
            db.query(FeedbackNote)
            .filter(FeedbackNote.author_id == current_user.id)
            .all()
        )
        notes_data = [
            {
                "id": n.id,
                "feedback_id": n.feedback_id,
                "content": n.content,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ]
        zf.writestr("notes.json", json.dumps(notes_data, indent=2))

        # ── preferences ──────────────────────────────────────────────────────
        prefs = (
            db.query(UserAlertPreference)
            .filter(UserAlertPreference.user_id == current_user.id)
            .all()
        )
        prefs_data = [
            {
                "alert_type": p.alert_type,
                "is_enabled": p.is_enabled,
                "channel_email": p.channel_email,
                "channel_slack": p.channel_slack,
                "channel_inapp": p.channel_inapp,
                "threshold_value": p.threshold_value,
            }
            for p in prefs
        ]
        prefs_payload = {
            "weekly_digest_enabled": current_user.weekly_digest_enabled,
            "daily_digest_enabled": current_user.daily_digest_enabled,
            "alert_channels": current_user.alert_channels,
            "alert_preferences": prefs_data,
        }
        zf.writestr("preferences.json", json.dumps(prefs_payload, indent=2))

        # ── reports ──────────────────────────────────────────────────────────
        reports = (
            db.query(Report)
            .filter(Report.created_by_user_id == current_user.id)
            .all()
        )
        reports_data = [
            {
                "id": r.id,
                "report_type": r.report_type,
                "title": r.title,
                "date_range_days": r.date_range_days,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
        zf.writestr("reports.json", json.dumps(reports_data, indent=2))

    buf.seek(0)
    filename = f"rereflect-export-{current_user.id}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Deletion Request
# ---------------------------------------------------------------------------

@router.post("/delete-request")
def request_deletion(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate the user account and schedule it for deletion in 30 days."""
    current_user.is_deactivated = True
    current_user.deletion_requested_at = datetime.utcnow()
    db.commit()

    # Best-effort confirmation email (non-blocking)
    try:
        from src.services.email_service import send_deletion_request_email
        send_deletion_request_email(current_user.email)
    except Exception:
        pass

    return {"message": "Deletion request received. Your account will be permanently deleted in 30 days."}


# ---------------------------------------------------------------------------
# Cancel Deletion
# ---------------------------------------------------------------------------

@router.post("/cancel-deletion")
def cancel_deletion(
    current_user: User = Depends(get_current_user_allow_deactivated),
    db: Session = Depends(get_db),
):
    """Reactivate a deactivated account and cancel the pending deletion."""
    current_user.is_deactivated = False
    current_user.deletion_requested_at = None
    db.commit()

    return {"message": "Deletion cancelled. Your account has been reactivated."}
