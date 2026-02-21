from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.api.dependencies import get_current_org
from pydantic import BaseModel
from typing import List
from celery import Celery
import os

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])

# Celery client for dispatching tasks to worker-service
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

celery_app = Celery("worker", broker=REDIS_URL)


# Schemas
class AnalyzeFeedbackRequest(BaseModel):
    feedback_ids: List[int]
    force: bool = False  # Force re-analysis of already-analyzed items


class AnalyzeFeedbackResponse(BaseModel):
    queued_count: int
    message: str


# Endpoints
@router.post("/", response_model=AnalyzeFeedbackResponse)
def analyze_feedback(
    data: AnalyzeFeedbackRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Queue feedback items for analysis via Celery worker."""

    if not data.feedback_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No feedback IDs provided"
        )

    # Get feedback items (with multi-tenant filtering)
    feedback_items = db.query(FeedbackItem).filter(
        FeedbackItem.id.in_(data.feedback_ids),
        FeedbackItem.organization_id == current_org.id
    ).all()

    if not feedback_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback items found"
        )

    # If force re-analysis, clear sentinel fields so worker doesn't skip them
    if data.force:
        for item in feedback_items:
            item.sentiment_label = None
            item.churn_risk_factors = None
        db.commit()

    # Dispatch to Celery worker
    queued_ids = [item.id for item in feedback_items]
    celery_app.send_task(
        "src.tasks.analysis.analyze_feedback_batch",
        args=[current_org.id, queued_ids],
    )

    return AnalyzeFeedbackResponse(
        queued_count=len(queued_ids),
        message=f"Queued {len(queued_ids)} feedback items for analysis"
    )


@router.post("/batch", response_model=AnalyzeFeedbackResponse)
def analyze_all_unanalyzed(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Queue all unanalyzed feedback for analysis via Celery worker."""

    # Get all feedback without sentiment
    unanalyzed = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id,
        FeedbackItem.sentiment_label.is_(None)
    ).all()

    if not unanalyzed:
        return AnalyzeFeedbackResponse(
            queued_count=0,
            message="No unanalyzed feedback found"
        )

    feedback_ids = [item.id for item in unanalyzed]

    # Dispatch to Celery worker
    celery_app.send_task(
        "src.tasks.analysis.analyze_feedback_batch",
        args=[current_org.id, feedback_ids],
    )

    return AnalyzeFeedbackResponse(
        queued_count=len(feedback_ids),
        message=f"Queued {len(feedback_ids)} feedback items for analysis"
    )
