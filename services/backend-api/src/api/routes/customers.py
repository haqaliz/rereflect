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
from src.models.customer_usage import CustomerUsage
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
    last_active_at: Optional[datetime] = None  # product-usage recency (from customer_usage rollup)
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
    usage_component: Optional[int] = None
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
    # CRM enrichment fields (HubSpot / Salesforce)
    crm_company_name: Optional[str] = None
    crm_lifecycle_stage: Optional[str] = None
    crm_arr: Optional[float] = None
    crm_renewal_date: Optional[datetime] = None
    crm_deal_name: Optional[str] = None
    crm_deal_stage: Optional[str] = None
    crm_deal_amount: Optional[float] = None
    crm_provider: Optional[str] = None


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
    # New fields added in timeline-service-v1 (additive only — all Optional)
    risk_level: Optional[str] = None
    reason_code: Optional[str] = None
    feature_name: Optional[str] = None
    source: Optional[str] = None
    gap_days: Optional[int] = None
    # CRM payload fields (additive — all Optional)
    company_name: Optional[str] = None
    renewal_date: Optional[datetime] = None
    deal_stage: Optional[str] = None
    arr: Optional[float] = None


class CustomerActivityResponse(BaseModel):
    events: List[ActivityEvent]


class TimelineResponse(BaseModel):
    events: List[ActivityEvent]
    next_cursor: Optional[str] = None


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

    # Fetch usage rollups for this page's customers in a single query (no N+1).
    page_emails = [r.customer_email for r in records]
    usage_map: dict[str, datetime] = {}
    if page_emails:
        usage_rows = (
            db.query(CustomerUsage.customer_email, CustomerUsage.last_active_at)
            .filter(
                CustomerUsage.organization_id == current_org.id,
                CustomerUsage.customer_email.in_(page_emails),
            )
            .all()
        )
        usage_map = {row.customer_email: row.last_active_at for row in usage_rows}

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
            last_active_at=usage_map.get(record.customer_email),
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

    # Delegate core field mapping to the shared serializer (no drift vs. public API).
    from src.services.customer_profile_serializer import serialize_customer_profile
    profile_data = serialize_customer_profile(record, db)

    # Load plan-gated action items on top (Business+ only).
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
        **{k: v for k, v in profile_data.items() if k in CustomerProfileResponse.model_fields},
        llm_actions=llm_actions,
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


def _timeline_event_to_activity(event) -> ActivityEvent:
    """Convert an internal TimelineEvent to the external ActivityEvent Pydantic model."""
    return ActivityEvent(
        type=event.type,
        timestamp=event.timestamp,
        description=event.description,
        feedback_id=event.feedback_id,
        old_score=event.old_score,
        new_score=event.new_score,
        risk_level=event.risk_level,
        reason_code=event.reason_code,
        feature_name=event.feature_name,
        source=event.source,
        gap_days=event.gap_days,
        company_name=getattr(event, "company_name", None),
        renewal_date=getattr(event, "renewal_date", None),
        deal_stage=getattr(event, "deal_stage", None),
        arr=getattr(event, "arr", None),
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
    """Get last 10 mixed activity events for a customer.

    Delegates to the shared timeline service — same external response shape
    as before, now including usage and churn events where present.
    """
    from src.services.customer_timeline_service import build_timeline

    timeline_events, _ = build_timeline(db, current_org.id, email, limit=10)
    activity_events = [_timeline_event_to_activity(e) for e in timeline_events]
    return CustomerActivityResponse(events=activity_events)


@router.get(
    "/{email}/timeline",
    response_model=TimelineResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def get_customer_timeline(
    email: str,
    before: Optional[str] = Query(None, description="Opaque cursor from a previous next_cursor"),
    limit: int = Query(20, ge=1, le=100, description="Max events per page (1-100)"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Cursor-paged, reverse-chronological timeline for a customer.

    Merges all event sources: feedback, health, churn, and notable usage events.

    Query params:
    - before: opaque cursor string (value of next_cursor from a previous response)
    - limit: number of events per page (default 20, max 100)

    Response:
    - events: list of timeline events (newest first)
    - next_cursor: opaque cursor to fetch the next page; null on the last page
    """
    from src.services.customer_timeline_service import build_timeline
    from fastapi import HTTPException

    # Validate / decode the before cursor early so we return 422 on bad input
    if before is not None:
        from src.services.customer_timeline_service import _decode_cursor
        try:
            _decode_cursor(before)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid cursor: {exc}",
            )

    timeline_events, next_cursor = build_timeline(
        db, current_org.id, email, before=before, limit=limit
    )
    activity_events = [_timeline_event_to_activity(e) for e in timeline_events]
    return TimelineResponse(events=activity_events, next_cursor=next_cursor)


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


# ---------------------------------------------------------------------------
# Churn Factors Endpoint
# ---------------------------------------------------------------------------

class AggregatedFactorItem(BaseModel):
    avg_score: float
    max: int
    description: str


class ChurnFactorsResponse(BaseModel):
    customer_email: str
    period_days: int
    feedback_count: int
    aggregated_factors: dict
    top_risk_drivers: List[str]


@router.get(
    "/{email}/churn-factors",
    response_model=ChurnFactorsResponse,
    dependencies=[Depends(require_feature("enhanced_churn_prediction"))],
)
def get_customer_churn_factors(
    email: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Get aggregated churn risk factor breakdown for a customer over the last 30 days.
    Pro+ only (enhanced_churn_prediction feature).
    """
    from src.models.feedback import FeedbackItem

    PERIOD_DAYS = 30
    now = datetime.utcnow()
    cutoff = now - timedelta(days=PERIOD_DAYS)

    # Get feedbacks with churn_risk_factors in the last 30 days
    feedbacks = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id,
        FeedbackItem.customer_email == email,
        FeedbackItem.churn_risk_factors.isnot(None),
        FeedbackItem.created_at >= cutoff,
    ).all()

    if not feedbacks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No churn factor data found for customer '{email}' in the last {PERIOD_DAYS} days",
        )

    FACTOR_MAXES = {
        "sentiment": 15,
        "churn_keywords": 15,
        "frustration_keywords": 10,
        "urgency": 10,
        "sentiment_trend": 15,
        "feedback_frequency": 10,
        "resolution_time": 10,
        "pain_severity": 10,
        "feature_density": 5,
    }

    # Aggregate factor scores across all feedbacks
    factor_sums: dict = {key: 0.0 for key in FACTOR_MAXES}
    factor_counts: dict = {key: 0 for key in FACTOR_MAXES}

    for fb in feedbacks:
        factors = fb.churn_risk_factors
        if not isinstance(factors, dict):
            continue
        for key in FACTOR_MAXES:
            if key in factors and "score" in factors[key]:
                factor_sums[key] += factors[key]["score"]
                factor_counts[key] += 1

    aggregated_factors = {}
    for key, max_pts in FACTOR_MAXES.items():
        count = factor_counts[key]
        avg = (factor_sums[key] / count) if count > 0 else 0.0
        pct = (avg / max_pts * 100) if max_pts > 0 else 0.0
        if pct > 75:
            desc = f"Consistently high {key.replace('_', ' ')} risk"
        elif pct > 40:
            desc = f"Moderate {key.replace('_', ' ')} risk"
        else:
            desc = f"Low {key.replace('_', ' ')} risk"
        aggregated_factors[key] = {
            "avg_score": round(avg, 2),
            "max": max_pts,
            "description": desc,
        }

    # Top risk drivers: factors with highest avg_score relative to max, top 3
    sorted_factors = sorted(
        aggregated_factors.items(),
        key=lambda x: x[1]["avg_score"] / x[1]["max"] if x[1]["max"] > 0 else 0,
        reverse=True,
    )
    top_risk_drivers = [k for k, _ in sorted_factors[:3] if sorted_factors[0][1]["avg_score"] > 0]

    return ChurnFactorsResponse(
        customer_email=email,
        period_days=PERIOD_DAYS,
        feedback_count=len(feedbacks),
        aggregated_factors=aggregated_factors,
        top_risk_drivers=top_risk_drivers,
    )


# ---------------------------------------------------------------------------
# Usage rollup + time-series endpoint  (aspect 3 — usage-rollup-and-score)
# ---------------------------------------------------------------------------

_VALID_USAGE_DAYS = {30, 60, 90}


class UsageRollupResponse(BaseModel):
    """Snapshot of the customer_usage rollup row."""
    customer_email: str
    usage_score: int
    events_total: int
    last_active_at: Optional[datetime]
    first_seen_at: Optional[datetime]
    login_count_7d: Optional[int]
    login_count_30d: Optional[int]
    active_days_7d: Optional[int]
    active_days_30d: Optional[int]
    distinct_features: Optional[List[str]]
    distinct_feature_count: Optional[int]
    updated_at: Optional[datetime]


class UsageTimeSeriesBucket(BaseModel):
    """Daily event count bucket for the chart."""
    date: str          # ISO date string, e.g. "2026-06-28"
    event_count: int


class CustomerUsageResponse(BaseModel):
    """Combined rollup + daily time series for the customer usage card."""
    rollup: UsageRollupResponse
    time_series: List[UsageTimeSeriesBucket]
    period_days: int


@router.get(
    "/{email}/usage",
    response_model=CustomerUsageResponse,
)
def get_customer_usage(
    email: str,
    days: int = Query(30, ge=1),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """
    Return the product-usage rollup and a daily event time series for a customer.

    Args:
        email: Customer email (URL-encoded if needed).
        days:  Rolling window size for the time series (must be 30, 60, or 90).
               Defaults to 30.

    Returns:
        JSON with ``rollup`` (snapshot) and ``time_series`` (daily buckets).

    Raises:
        422 if ``days`` is not one of the valid values.
        404 if no usage rollup exists for this customer in the caller's org.
    """
    from src.models.customer_usage import CustomerUsage as CustomerUsageModel
    from src.models.usage_event import UsageEvent as UsageEventModel
    from collections import defaultdict

    if days not in _VALID_USAGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'days' must be one of {sorted(_VALID_USAGE_DAYS)}; got {days}.",
        )

    # Fetch rollup (org-scoped)
    rollup = (
        db.query(CustomerUsageModel)
        .filter_by(organization_id=current_org.id, customer_email=email)
        .first()
    )
    if rollup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No usage data found for customer '{email}'.",
        )

    # Build daily time series from raw events within the window
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    events = (
        db.query(UsageEventModel)
        .filter(
            UsageEventModel.organization_id == current_org.id,
            UsageEventModel.customer_email == email,
            UsageEventModel.occurred_at >= cutoff,
        )
        .all()
    )

    # Bucket events by calendar day
    counts: dict = defaultdict(int)
    for ev in events:
        if ev.occurred_at:
            day_key = ev.occurred_at.date().isoformat()
            counts[day_key] += 1

    time_series = [
        UsageTimeSeriesBucket(date=day, event_count=cnt)
        for day, cnt in sorted(counts.items())
    ]

    rollup_response = UsageRollupResponse(
        customer_email=rollup.customer_email,
        usage_score=rollup.usage_score,
        events_total=rollup.events_total,
        last_active_at=rollup.last_active_at,
        first_seen_at=rollup.first_seen_at,
        login_count_7d=rollup.login_count_7d,
        login_count_30d=rollup.login_count_30d,
        active_days_7d=rollup.active_days_7d,
        active_days_30d=rollup.active_days_30d,
        distinct_features=rollup.distinct_features,
        distinct_feature_count=rollup.distinct_feature_count,
        updated_at=rollup.updated_at,
    )

    return CustomerUsageResponse(
        rollup=rollup_response,
        time_series=time_series,
        period_days=days,
    )
