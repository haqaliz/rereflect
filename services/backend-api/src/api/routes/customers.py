"""
Customer 360 API routes.
Provides list, profile, history, feedbacks, and activity endpoints.
"""
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, asc, desc, or_
from pydantic import BaseModel

from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.models.customer_analysis_action import CustomerAnalysisAction
from src.models.organization import Organization
from src.api.dependencies import get_current_org, get_current_user, require_feature, require_system_admin
from src.models.user import User
from src.config.plans import has_feature

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

# Valid sort fields and risk levels for query validation
VALID_SORT_FIELDS = {"health_score", "feedback_count", "last_feedback_at", "customer_email"}
VALID_RISK_LEVELS = {"healthy", "moderate", "at_risk", "critical"}
VALID_HISTORY_DAYS = {30, 60, 90}


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class SentimentTrend(BaseModel):
    direction: str
    change_percent: float


class CustomerListItem(BaseModel):
    customer_email: str
    customer_name: Optional[str] = None
    health_score: int
    risk_level: str
    confidence_level: str
    feedback_count: int
    last_feedback_at: Optional[datetime] = None
    sentiment_trend: SentimentTrend
    is_archived: bool
    has_llm_analysis: bool


class RiskDistribution(BaseModel):
    healthy: int
    moderate: int
    at_risk: int
    critical: int


class CustomerListSummary(BaseModel):
    total_customers: int
    avg_health_score: int
    risk_distribution: RiskDistribution


class CustomerListResponse(BaseModel):
    items: List[CustomerListItem]
    total: int
    page: int
    page_size: int
    summary: CustomerListSummary


class ActionItemResponse(BaseModel):
    id: int
    action_text: str
    status: str
    completed_by: Optional[int] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CustomerProfileResponse(BaseModel):
    customer_email: str
    customer_name: Optional[str] = None
    health_score: int
    risk_level: str
    confidence_level: str
    feedback_count: int
    last_feedback_at: Optional[datetime] = None
    churn_risk_component: int
    sentiment_component: int
    resolution_component: int
    frequency_component: int
    # Structured LLM analysis fields
    llm_analysis_summary: Optional[str] = None
    llm_recommended_actions: Optional[List[str]] = None
    llm_risk_drivers: Optional[List[str]] = None
    llm_urgency: Optional[str] = None
    llm_analysis_type: Optional[str] = None
    llm_analyzed_at: Optional[datetime] = None
    llm_actions: Optional[List[ActionItemResponse]] = None  # Business+ only
    # Legacy field (transition period)
    llm_analysis: Optional[str] = None
    is_archived: bool
    created_at: Optional[datetime] = None


class HealthHistoryItem(BaseModel):
    health_score: int
    churn_risk_component: Optional[int] = None
    sentiment_component: Optional[int] = None
    resolution_component: Optional[int] = None
    frequency_component: Optional[int] = None
    risk_level: Optional[str] = None
    recorded_at: datetime


class CustomerHistoryResponse(BaseModel):
    history: List[HealthHistoryItem]
    period_start: datetime
    period_end: datetime


class FeedbackItem(BaseModel):
    id: int
    text_snippet: str
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    churn_risk_score: Optional[int] = None
    workflow_status: str
    created_at: datetime
    source: Optional[str] = None


class CustomerFeedbacksResponse(BaseModel):
    feedbacks: List[FeedbackItem]
    total_count: int
    view_all_url: str


class ActivityEvent(BaseModel):
    type: str
    description: str
    timestamp: datetime
    feedback_id: Optional[int] = None
    old_score: Optional[int] = None
    new_score: Optional[int] = None


class CustomerActivityResponse(BaseModel):
    events: List[ActivityEvent]


class AnalyzeResponse(BaseModel):
    message: str
    estimated_wait_seconds: int


class BatchAnalyzeResponse(BaseModel):
    message: str
    customer_count: int


class ActionUpdateRequest(BaseModel):
    status: str  # "completed" or "dismissed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_sentiment_trend_for_customer(org_id: int, customer_email: str, db: Session) -> dict:
    from src.services.health_score_service import compute_sentiment_trend
    return compute_sentiment_trend(org_id, customer_email, db)


def _queue_llm_analysis(org_id: int, customer_email: str) -> str:
    """Queue an LLM analysis task for a customer. Returns task ID."""
    try:
        from src.background import get_celery_app
        app = get_celery_app()
        result = app.send_task(
            "src.tasks.insights.analyze_customer_health",
            args=[org_id, customer_email],
        )
        return result.id
    except Exception:
        # If Celery is not available (e.g., in tests), return a placeholder ID
        import uuid
        return str(uuid.uuid4())


def _get_summary(org_id: int, include_archived: bool, db: Session) -> CustomerListSummary:
    base_q = db.query(CustomerHealth).filter(CustomerHealth.organization_id == org_id)
    if not include_archived:
        base_q = base_q.filter(CustomerHealth.is_archived == False)

    total = base_q.count()
    avg_score = base_q.with_entities(func.avg(CustomerHealth.health_score)).scalar() or 0

    dist = {level: 0 for level in ("healthy", "moderate", "at_risk", "critical")}
    rows = base_q.with_entities(CustomerHealth.risk_level, func.count(CustomerHealth.id)).group_by(
        CustomerHealth.risk_level
    ).all()
    for risk_level, count in rows:
        if risk_level in dist:
            dist[risk_level] = count

    return CustomerListSummary(
        total_customers=total,
        avg_health_score=round(avg_score),
        risk_distribution=RiskDistribution(**dist),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=CustomerListResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("health_score"),
    sort_order: str = Query("asc"),
    risk_level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all customers with health scores."""
    if sort_by not in VALID_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort_by value '{sort_by}'. Must be one of: {', '.join(sorted(VALID_SORT_FIELDS))}",
        )

    if risk_level is not None and risk_level not in VALID_RISK_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid risk_level '{risk_level}'. Must be one of: {', '.join(sorted(VALID_RISK_LEVELS))}",
        )

    query = db.query(CustomerHealth).filter(CustomerHealth.organization_id == current_org.id)

    if not include_archived:
        query = query.filter(CustomerHealth.is_archived == False)

    if risk_level:
        query = query.filter(CustomerHealth.risk_level == risk_level)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                CustomerHealth.customer_email.ilike(pattern),
                CustomerHealth.customer_name.ilike(pattern),
            )
        )

    total = query.count()

    sort_column_map = {
        "health_score": CustomerHealth.health_score,
        "feedback_count": CustomerHealth.feedback_count,
        "last_feedback_at": CustomerHealth.last_feedback_at,
        "customer_email": CustomerHealth.customer_email,
    }
    sort_col = sort_column_map[sort_by]
    sort_fn = asc if sort_order == "asc" else desc
    query = query.order_by(sort_fn(sort_col))

    offset = (page - 1) * page_size
    records = query.offset(offset).limit(page_size).all()

    items = []
    for record in records:
        trend = _compute_sentiment_trend_for_customer(current_org.id, record.customer_email, db)
        items.append(CustomerListItem(
            customer_email=record.customer_email,
            customer_name=record.customer_name,
            health_score=record.health_score,
            risk_level=record.risk_level,
            confidence_level=record.confidence_level or "low",
            feedback_count=record.feedback_count,
            last_feedback_at=record.last_feedback_at,
            sentiment_trend=SentimentTrend(**trend),
            is_archived=record.is_archived or False,
            has_llm_analysis=record.llm_analysis_data is not None or record.llm_analysis is not None,
        ))

    summary = _get_summary(current_org.id, include_archived, db)

    return CustomerListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        summary=summary,
    )


@router.get(
    "/{email}",
    response_model=CustomerProfileResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def get_customer_profile(
    email: str,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full profile for a customer by email."""
    record = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.customer_email == email,
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health record found for customer '{email}'",
        )

    # Extract structured LLM fields from JSON
    analysis_data = record.llm_analysis_data or {}
    llm_analysis_summary = analysis_data.get("analysis") if analysis_data else None
    llm_recommended_actions = analysis_data.get("recommended_actions") if analysis_data else None
    llm_risk_drivers = analysis_data.get("risk_drivers") if analysis_data else None
    llm_urgency = analysis_data.get("estimated_urgency") if analysis_data else None
    llm_analysis_type = analysis_data.get("analysis_type") if analysis_data else None

    # Load action items only for Business+ plans
    llm_actions = None
    if has_feature(current_org.plan, "ai_analysis_actions"):
        action_records = db.query(CustomerAnalysisAction).filter(
            CustomerAnalysisAction.customer_health_id == record.id,
        ).order_by(CustomerAnalysisAction.created_at.desc()).all()

        llm_actions = [
            ActionItemResponse(
                id=a.id,
                action_text=a.action_text,
                status=a.status,
                completed_by=a.completed_by,
                completed_at=a.completed_at,
                created_at=a.created_at,
            )
            for a in action_records
        ]

    return CustomerProfileResponse(
        customer_email=record.customer_email,
        customer_name=record.customer_name,
        health_score=record.health_score,
        risk_level=record.risk_level,
        confidence_level=record.confidence_level or "low",
        feedback_count=record.feedback_count,
        last_feedback_at=record.last_feedback_at,
        churn_risk_component=record.churn_risk_component or 50,
        sentiment_component=record.sentiment_component or 50,
        resolution_component=record.resolution_component or 50,
        frequency_component=record.frequency_component or 50,
        llm_analysis_summary=llm_analysis_summary,
        llm_recommended_actions=llm_recommended_actions,
        llm_risk_drivers=llm_risk_drivers,
        llm_urgency=llm_urgency,
        llm_analysis_type=llm_analysis_type,
        llm_analyzed_at=record.llm_analyzed_at,
        llm_actions=llm_actions,
        llm_analysis=record.llm_analysis,
        is_archived=record.is_archived or False,
        created_at=record.created_at,
    )


@router.get(
    "/{email}/history",
    response_model=CustomerHistoryResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def get_customer_history(
    email: str,
    days: int = Query(30),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get health score history for a customer. days must be 30, 60, or 90."""
    if days not in VALID_HISTORY_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid days value '{days}'. Must be one of: {sorted(VALID_HISTORY_DAYS)}",
        )

    from src.models.customer_health_history import CustomerHealthHistory

    now = datetime.utcnow()
    period_start = now - timedelta(days=days)
    period_end = now

    # Find CustomerHealth record for this org+email
    health = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.customer_email == email,
    ).first()

    if not health:
        # Return empty history even if not found (more useful than 404)
        return CustomerHistoryResponse(history=[], period_start=period_start, period_end=period_end)

    records = db.query(CustomerHealthHistory).filter(
        CustomerHealthHistory.customer_health_id == health.id,
        CustomerHealthHistory.recorded_at >= period_start,
        CustomerHealthHistory.recorded_at <= period_end,
    ).order_by(asc(CustomerHealthHistory.recorded_at)).all()

    history = [
        HealthHistoryItem(
            health_score=r.health_score,
            churn_risk_component=r.churn_risk_component,
            sentiment_component=r.sentiment_component,
            resolution_component=r.resolution_component,
            frequency_component=r.frequency_component,
            risk_level=r.risk_level,
            recorded_at=r.recorded_at,
        )
        for r in records
    ]

    return CustomerHistoryResponse(
        history=history,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/{email}/feedbacks",
    response_model=CustomerFeedbacksResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def get_customer_feedbacks(
    email: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get last 15 feedbacks for a customer (compact view)."""
    from src.models.feedback import FeedbackItem as FeedbackModel

    total = db.query(func.count(FeedbackModel.id)).filter(
        FeedbackModel.organization_id == current_org.id,
        FeedbackModel.customer_email == email,
    ).scalar() or 0

    records = db.query(FeedbackModel).filter(
        FeedbackModel.organization_id == current_org.id,
        FeedbackModel.customer_email == email,
    ).order_by(desc(FeedbackModel.created_at)).limit(15).all()

    def truncate_text(text: str, max_len: int = 100) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    feedbacks = [
        FeedbackItem(
            id=r.id,
            text_snippet=truncate_text(r.text),
            sentiment_label=r.sentiment_label,
            sentiment_score=r.sentiment_score,
            churn_risk_score=r.churn_risk_score,
            workflow_status=r.workflow_status,
            created_at=r.created_at,
            source=r.source,
        )
        for r in records
    ]

    view_all_url = f"/feedbacks?customer_email={email}"

    return CustomerFeedbacksResponse(
        feedbacks=feedbacks,
        total_count=total,
        view_all_url=view_all_url,
    )


@router.get(
    "/{email}/activity",
    response_model=CustomerActivityResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def get_customer_activity(
    email: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get last 10 mixed activity events for a customer."""
    from src.models.feedback import FeedbackItem as FeedbackModel
    from src.models.feedback_workflow_event import FeedbackWorkflowEvent
    from src.models.customer_health_history import CustomerHealthHistory

    events = []

    # 1. feedback_created events
    recent_feedbacks = db.query(FeedbackModel).filter(
        FeedbackModel.organization_id == current_org.id,
        FeedbackModel.customer_email == email,
    ).order_by(desc(FeedbackModel.created_at)).limit(10).all()

    for fb in recent_feedbacks:
        events.append(ActivityEvent(
            type="feedback_created",
            description="New feedback submitted",
            timestamp=fb.created_at,
            feedback_id=fb.id,
        ))

    # 2. status_changed events from workflow
    feedback_ids = [fb.id for fb in recent_feedbacks]
    if feedback_ids:
        status_events = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.organization_id == current_org.id,
            FeedbackWorkflowEvent.feedback_id.in_(feedback_ids),
            FeedbackWorkflowEvent.event_type == "status_changed",
        ).order_by(desc(FeedbackWorkflowEvent.created_at)).limit(10).all()

        for ev in status_events:
            events.append(ActivityEvent(
                type="status_changed",
                description=f"Feedback #{ev.feedback_id} moved to {ev.new_value}",
                timestamp=ev.created_at,
                feedback_id=ev.feedback_id,
            ))

    # 3. health_score_changed events from history
    health = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.customer_email == email,
    ).first()

    if health:
        hist_records = db.query(CustomerHealthHistory).filter(
            CustomerHealthHistory.customer_health_id == health.id,
        ).order_by(desc(CustomerHealthHistory.recorded_at)).limit(10).all()

        for i, hist in enumerate(hist_records):
            prev_score = hist_records[i + 1].health_score if i + 1 < len(hist_records) else None
            desc_text = f"Health score changed to {hist.health_score}"
            if prev_score is not None:
                desc_text = f"Health score changed from {prev_score} to {hist.health_score}"
            events.append(ActivityEvent(
                type="health_score_changed",
                description=desc_text,
                timestamp=hist.recorded_at,
                old_score=prev_score,
                new_score=hist.health_score,
            ))

        # 4. llm_analysis_generated event
        if health.llm_analyzed_at:
            events.append(ActivityEvent(
                type="llm_analysis_generated",
                description="AI analysis generated",
                timestamp=health.llm_analyzed_at,
            ))

        # 5. action_completed events
        completed_actions = db.query(CustomerAnalysisAction).filter(
            CustomerAnalysisAction.customer_health_id == health.id,
            CustomerAnalysisAction.status.in_(["completed", "dismissed"]),
        ).order_by(desc(CustomerAnalysisAction.completed_at)).limit(10).all()

        for action in completed_actions:
            if action.completed_at:
                verb = "completed" if action.status == "completed" else "dismissed"
                events.append(ActivityEvent(
                    type="action_completed",
                    description=f"Action {verb}: {action.action_text[:60]}",
                    timestamp=action.completed_at,
                ))

    # Sort all events by timestamp descending and take top 10
    events.sort(key=lambda e: e.timestamp, reverse=True)
    events = events[:10]

    return CustomerActivityResponse(events=events)


@router.post(
    "/{email}/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_feature("churn_llm_insights"))],
)
def analyze_customer(
    email: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Queue an on-demand LLM analysis for a customer. Returns 202 immediately."""
    record = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.customer_email == email,
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health record found for customer '{email}'",
        )

    # 24h cooldown check
    if record.llm_analyzed_at:
        hours_since = (datetime.utcnow() - record.llm_analyzed_at).total_seconds() / 3600
        if hours_since < 24:
            hours_remaining = round(24 - hours_since, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Analysis was run {round(hours_since, 1)}h ago. Try again in {hours_remaining}h.",
            )

    _queue_llm_analysis(current_org.id, email)

    return AnalyzeResponse(
        message="Analysis queued",
        estimated_wait_seconds=15,
    )


@router.post(
    "/batch-analyze",
    response_model=BatchAnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_feature("churn_llm_insights")), Depends(require_system_admin)],
)
def batch_analyze_customers(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Queue LLM analysis for all customers in the organization.

    Dispatches a single batch_churn_analysis Celery task for this org.
    The task processes customers with missing or stale analysis (>7 days old),
    using the appropriate prompt based on health score tier.
    Returns 202 with the count of customers eligible for analysis.
    Requires system admin role.
    """
    customer_count = db.query(func.count(CustomerHealth.id)).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.is_archived == False,
    ).scalar() or 0

    try:
        from src.background import get_celery_app
        app = get_celery_app()
        app.send_task(
            "src.tasks.insights.batch_churn_analysis",
            args=[current_org.id],
        )
    except Exception:
        pass

    return BatchAnalyzeResponse(
        message="Analysis queued for all customers",
        customer_count=customer_count,
    )


@router.patch(
    "/{email}/actions/{action_id}",
    response_model=ActionItemResponse,
    dependencies=[Depends(require_feature("ai_analysis_actions"))],
)
def update_action_item(
    email: str,
    action_id: int,
    body: ActionUpdateRequest,
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the status of an analysis action item (complete or dismiss)."""
    if body.status not in ("completed", "dismissed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Status must be 'completed' or 'dismissed'",
        )

    # Verify the customer belongs to this org
    health = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.customer_email == email,
    ).first()

    if not health:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health record found for customer '{email}'",
        )

    action = db.query(CustomerAnalysisAction).filter(
        CustomerAnalysisAction.id == action_id,
        CustomerAnalysisAction.customer_health_id == health.id,
    ).first()

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action item {action_id} not found",
        )

    action.status = body.status
    action.completed_by = current_user.id
    action.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(action)

    return ActionItemResponse(
        id=action.id,
        action_text=action.action_text,
        status=action.status,
        completed_by=action.completed_by,
        completed_at=action.completed_at,
        created_at=action.created_at,
    )
