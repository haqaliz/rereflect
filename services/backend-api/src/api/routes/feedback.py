from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, cast, func
from sqlalchemy.dialects.postgresql import JSONB
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.feedback_source import FeedbackSource
from src.models.organization import Organization
from src.api.dependencies import get_current_org, check_feedback_limit, track_feedback_usage, get_current_usage
from src.models.usage import UsageRecord
from pydantic import BaseModel
from datetime import datetime
import sys
import os
import csv
import io

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

# Lazy import to add analysis-engine to path only when needed
def get_sentiment_analyzer():
    """Get SentimentAnalyzer with lazy import."""
    analysis_engine_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../analysis-engine"))
    if analysis_engine_path not in sys.path:
        sys.path.insert(0, analysis_engine_path)
    from analyzer.sentiment import SentimentAnalyzer
    return SentimentAnalyzer()


def get_categorizers():
    """Get categorizers with lazy import."""
    analysis_engine_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../analysis-engine"))
    if analysis_engine_path not in sys.path:
        sys.path.insert(0, analysis_engine_path)
    from analyzer.categorizer import PainPointCategorizer, FeatureRequestCategorizer, UrgentCategorizer
    return PainPointCategorizer(), FeatureRequestCategorizer(), UrgentCategorizer()


# Helper function for automatic analysis
def analyze_single_feedback(feedback: FeedbackItem, db: Session) -> None:
    """Automatically analyze a single feedback item with categorization."""
    try:
        sentiment_analyzer = get_sentiment_analyzer()
        sentiment = sentiment_analyzer.analyze(feedback.text)

        feedback.sentiment_score = sentiment['compound']
        feedback.sentiment_label = sentiment['label']

        # Simple urgency detection based on keywords and negative sentiment
        urgent_keywords = ['urgent', 'critical', 'broken', 'crash', 'bug', 'error', 'failing', 'down', 'cannot', 'can\'t', 'won\'t', 'doesn\'t']
        text_lower = feedback.text.lower()
        has_urgent_keyword = any(keyword in text_lower for keyword in urgent_keywords)
        is_very_negative = sentiment['compound'] < -0.5

        feedback.is_urgent = has_urgent_keyword and is_very_negative

        # Extract pain points (problems, bugs, complaints)
        pain_keywords = ['bug', 'error', 'broken', 'crash', 'issue', 'problem', 'fail', 'not working', 'doesn\'t work', 'can\'t', 'cannot', 'won\'t', 'terrible', 'awful', 'slow', 'confusing', 'frustrating']
        if any(keyword in text_lower for keyword in pain_keywords) or sentiment['compound'] < -0.3:
            # Extract a short issue description from the text
            feedback.extracted_issue = feedback.text[:100] + ('...' if len(feedback.text) > 100 else '')

        # Get categorizers and categorize
        pain_point_categorizer, feature_request_categorizer, urgent_categorizer = get_categorizers()

        # Categorize based on sentiment
        if feedback.sentiment_label == 'negative':
            # Categorize as pain point
            pain_result = pain_point_categorizer.categorize(feedback.text)
            feedback.pain_point_category = pain_result.category
            feedback.pain_point_severity = pain_result.level
            feedback.pain_point_text = pain_result.text
            feedback.categorization_confidence = pain_result.confidence

        elif feedback.sentiment_label == 'positive':
            # Categorize as feature request
            feature_result = feature_request_categorizer.categorize(feedback.text)
            feedback.feature_request_category = feature_result.category
            feedback.feature_request_priority = feature_result.level
            feedback.feature_request_text = feature_result.text
            feedback.categorization_confidence = feature_result.confidence

        # If urgent, also categorize urgent type
        if feedback.is_urgent:
            urgent_result = urgent_categorizer.categorize(feedback.text, feedback.sentiment_score or 0.0)
            feedback.urgent_category = urgent_result.category
            feedback.urgent_response_time = urgent_result.level
            # Update confidence to be the higher of the two
            if feedback.categorization_confidence is None or urgent_result.confidence > feedback.categorization_confidence:
                feedback.categorization_confidence = urgent_result.confidence

        db.commit()
    except Exception as e:
        # If analysis fails, just continue without analysis
        print(f"Auto-analysis failed: {str(e)}")
        pass


# Schemas
class FeedbackCreateRequest(BaseModel):
    text: str
    source: Optional[str] = "manual"


class FeedbackResponse(BaseModel):
    id: int
    organization_id: int
    text: str
    source: Optional[str]
    # Source tracking
    source_id: Optional[int] = None
    source_name: Optional[str] = None  # From FeedbackSource.name
    source_metadata: Optional[dict] = None  # {author_name, channel_name, url, etc.}
    sentiment_score: Optional[float]
    sentiment_label: Optional[str]
    extracted_issue: Optional[str]
    tags: Optional[List[str]]
    is_urgent: bool
    created_at: datetime
    # Pain point categorization
    pain_point_category: Optional[str]
    pain_point_severity: Optional[str]
    pain_point_text: Optional[str]
    # Feature request categorization
    feature_request_category: Optional[str]
    feature_request_priority: Optional[str]
    feature_request_text: Optional[str]
    # Urgent categorization
    urgent_category: Optional[str]
    urgent_response_time: Optional[str]
    # Confidence score
    categorization_confidence: Optional[float]
    # Churn risk
    churn_risk_score: Optional[int] = None
    suggested_action: Optional[str] = None
    # Workflow
    workflow_status: str = "new"
    assigned_to: Optional[int] = None
    assigned_to_email: Optional[str] = None

    class Config:
        from_attributes = True


class FeedbackListResponse(BaseModel):
    items: List[FeedbackResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CSVImportResponse(BaseModel):
    total_rows: int
    imported_count: int
    failed_count: int
    errors: List[str]


# Endpoints
@router.post("/", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(
    data: FeedbackCreateRequest,
    current_org: Organization = Depends(get_current_org),
    usage: UsageRecord = Depends(get_current_usage),
    _limit_check: bool = Depends(check_feedback_limit),
    db: Session = Depends(get_db)
):
    """Create a new feedback item. Celery worker will analyze it automatically."""
    from src.background import queue_analyze_feedback
    from src.config.plans import get_feedback_limit

    feedback = FeedbackItem(
        organization_id=current_org.id,
        text=data.text,
        source=data.source
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # Track usage
    plan = current_org.plan or "free"
    limit = get_feedback_limit(plan)
    if limit is None:
        usage.feedback_count += 1
    elif usage.feedback_count < limit:
        usage.feedback_count += 1
    else:
        usage.overage_feedback += 1
    db.commit()

    # Auto-assign if enabled
    try:
        if current_org.auto_assignment_enabled:
            from src.services.workflow_service import auto_assign_feedback
            user_id = auto_assign_feedback(db, feedback, current_org.id)
            if user_id:
                feedback.assigned_to = user_id
                db.commit()
                db.refresh(feedback)
    except Exception:
        pass

    # Invalidate dashboard/analytics cache for this org
    from src.services.cache_service import cache_invalidate
    cache_invalidate(f"dashboard:{current_org.id}:*")
    cache_invalidate(f"analytics:{current_org.id}:*")

    # Queue for analysis via Celery worker
    queue_analyze_feedback(feedback.id)

    return feedback


@router.get("/", response_model=FeedbackListResponse)
def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: Optional[str] = Query(None, description="Search in feedback text and extracted issue"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment: positive, neutral, negative"),
    source: Optional[str] = Query(None, description="Filter by source"),
    is_urgent: Optional[bool] = Query(None, description="Filter by urgent status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    pain_point_category: Optional[str] = Query(None, description="Filter by pain point category"),
    pain_point_severity: Optional[str] = Query(None, description="Filter by pain point severity"),
    feature_request_category: Optional[str] = Query(None, description="Filter by feature request category"),
    feature_request_priority: Optional[str] = Query(None, description="Filter by feature request priority"),
    urgent_category: Optional[str] = Query(None, description="Filter by urgent category"),
    urgent_response_time: Optional[str] = Query(None, description="Filter by urgent response time"),
    churn_risk_min: Optional[int] = Query(None, ge=0, le=100, description="Minimum churn risk score"),
    churn_risk_max: Optional[int] = Query(None, ge=0, le=100, description="Maximum churn risk score"),
    workflow_status: Optional[str] = Query(None, description="Filter by workflow status: new, in_review, resolved, closed"),
    assigned_to: Optional[int] = Query(None, description="Filter by assigned user ID"),
    sort_by: Optional[str] = Query(None, description="Sort by field: created_at, sentiment_score, text, churn_risk_score, workflow_status"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """List feedback items with pagination and filters."""

    # Base query
    query = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id
    )

    # Apply search filter (case-insensitive search in text and extracted_issue)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (FeedbackItem.text.ilike(search_term)) |
            (FeedbackItem.extracted_issue.ilike(search_term))
        )

    # Apply filters
    if sentiment:
        query = query.filter(FeedbackItem.sentiment_label == sentiment)

    if source:
        query = query.filter(FeedbackItem.source == source)

    if is_urgent is not None:
        query = query.filter(FeedbackItem.is_urgent == is_urgent)

    if tag:
        # Filter by tag using PostgreSQL JSONB containment operator (@>)
        # Cast the tags column to JSONB and check if it contains the tag
        query = query.filter(
            cast(FeedbackItem.tags, JSONB).op('@>')(cast([tag], JSONB))
        )

    # Category filters
    if pain_point_category:
        query = query.filter(FeedbackItem.pain_point_category == pain_point_category)

    if pain_point_severity:
        query = query.filter(FeedbackItem.pain_point_severity == pain_point_severity)

    if feature_request_category:
        query = query.filter(FeedbackItem.feature_request_category == feature_request_category)

    if feature_request_priority:
        query = query.filter(FeedbackItem.feature_request_priority == feature_request_priority)

    if urgent_category:
        query = query.filter(FeedbackItem.urgent_category == urgent_category)

    if urgent_response_time:
        query = query.filter(FeedbackItem.urgent_response_time == urgent_response_time)

    if churn_risk_min is not None:
        query = query.filter(FeedbackItem.churn_risk_score >= churn_risk_min)

    if churn_risk_max is not None:
        query = query.filter(FeedbackItem.churn_risk_score <= churn_risk_max)

    if workflow_status:
        query = query.filter(FeedbackItem.workflow_status == workflow_status)

    if assigned_to is not None:
        query = query.filter(FeedbackItem.assigned_to == assigned_to)

    # Get total count
    total = query.count()

    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Apply sorting
    sort_column_map = {
        'created_at': FeedbackItem.created_at,
        'sentiment_score': FeedbackItem.sentiment_score,
        'text': FeedbackItem.text,
        'source': FeedbackItem.source,
        'id': FeedbackItem.id,
        'churn_risk_score': FeedbackItem.churn_risk_score,
        'workflow_status': FeedbackItem.workflow_status,
    }
    sort_column = sort_column_map.get(sort_by, FeedbackItem.created_at)
    order_func = asc if sort_order == 'asc' else desc

    # Eager load relationships to avoid N+1 queries
    query = query.options(
        joinedload(FeedbackItem.feedback_source),
        joinedload(FeedbackItem.assigned_user),
    )

    # Get items
    items = query.order_by(order_func(sort_column)).offset(offset).limit(page_size).all()

    # Build response using eager-loaded relationships (with fallback to batch queries)
    source_map = {}
    assignee_map = {}

    # Fallback: batch query if relationships return None for items that should have data
    source_ids = [item.source_id for item in items if item.source_id and not item.feedback_source]
    if source_ids:
        sources = db.query(FeedbackSource).filter(FeedbackSource.id.in_(source_ids)).all()
        source_map = {s.id: s.name for s in sources}

    from src.models.user import User
    assignee_ids = [item.assigned_to for item in items if item.assigned_to and not item.assigned_user]
    if assignee_ids:
        users = db.query(User).filter(User.id.in_(assignee_ids)).all()
        assignee_map = {u.id: u.email for u in users}

    response_items = []
    for item in items:
        # Use eager-loaded relationship first, fallback to map
        source_name = None
        if item.source_id:
            if item.feedback_source:
                source_name = item.feedback_source.name
            else:
                source_name = source_map.get(item.source_id)

        assigned_to_email = None
        if item.assigned_to:
            if item.assigned_user:
                assigned_to_email = item.assigned_user.email
            else:
                assigned_to_email = assignee_map.get(item.assigned_to)

        item_dict = {
            "id": item.id,
            "organization_id": item.organization_id,
            "text": item.text,
            "source": item.source,
            "source_id": item.source_id,
            "source_name": source_name,
            "source_metadata": item.source_metadata,
            "sentiment_score": item.sentiment_score,
            "sentiment_label": item.sentiment_label,
            "extracted_issue": item.extracted_issue,
            "tags": item.tags,
            "is_urgent": item.is_urgent,
            "created_at": item.created_at,
            "pain_point_category": item.pain_point_category,
            "pain_point_severity": item.pain_point_severity,
            "pain_point_text": item.pain_point_text,
            "feature_request_category": item.feature_request_category,
            "feature_request_priority": item.feature_request_priority,
            "feature_request_text": item.feature_request_text,
            "urgent_category": item.urgent_category,
            "urgent_response_time": item.urgent_response_time,
            "categorization_confidence": item.categorization_confidence,
            "churn_risk_score": item.churn_risk_score,
            "suggested_action": item.suggested_action,
            "workflow_status": item.workflow_status,
            "assigned_to": item.assigned_to,
            "assigned_to_email": assigned_to_email,
        }
        response_items.append(FeedbackResponse(**item_dict))

    return FeedbackListResponse(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
def get_feedback(
    feedback_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Get a single feedback item by ID."""

    feedback = db.query(FeedbackItem).filter(
        FeedbackItem.id == feedback_id,
        FeedbackItem.organization_id == current_org.id  # Multi-tenant isolation
    ).first()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found"
        )

    # Get source name if source_id exists
    source_name = None
    if feedback.source_id:
        source = db.query(FeedbackSource).filter(FeedbackSource.id == feedback.source_id).first()
        if source:
            source_name = source.name

    # Get assignee email if assigned
    assigned_to_email = None
    if feedback.assigned_to:
        from src.models.user import User
        assignee_user = db.query(User).filter(User.id == feedback.assigned_to).first()
        assigned_to_email = assignee_user.email if assignee_user else None

    return FeedbackResponse(
        id=feedback.id,
        organization_id=feedback.organization_id,
        text=feedback.text,
        source=feedback.source,
        source_id=feedback.source_id,
        source_name=source_name,
        source_metadata=feedback.source_metadata,
        sentiment_score=feedback.sentiment_score,
        sentiment_label=feedback.sentiment_label,
        extracted_issue=feedback.extracted_issue,
        tags=feedback.tags,
        is_urgent=feedback.is_urgent,
        created_at=feedback.created_at,
        pain_point_category=feedback.pain_point_category,
        pain_point_severity=feedback.pain_point_severity,
        pain_point_text=feedback.pain_point_text,
        feature_request_category=feedback.feature_request_category,
        feature_request_priority=feedback.feature_request_priority,
        feature_request_text=feedback.feature_request_text,
        urgent_category=feedback.urgent_category,
        urgent_response_time=feedback.urgent_response_time,
        categorization_confidence=feedback.categorization_confidence,
        churn_risk_score=feedback.churn_risk_score,
        suggested_action=feedback.suggested_action,
        workflow_status=feedback.workflow_status,
        assigned_to=feedback.assigned_to,
        assigned_to_email=assigned_to_email,
    )


@router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(
    feedback_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Delete a feedback item."""

    feedback = db.query(FeedbackItem).filter(
        FeedbackItem.id == feedback_id,
        FeedbackItem.organization_id == current_org.id  # Multi-tenant isolation
    ).first()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found"
        )

    db.delete(feedback)
    db.commit()

    return None


@router.post("/bulk-delete")
def bulk_delete_feedback(
    data: dict,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Delete multiple feedback items."""
    feedback_ids = data.get('feedback_ids', [])

    if not feedback_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No feedback IDs provided"
        )

    # Nullify references in slack_alert_logs before deleting
    from src.models.integration import SlackAlertLog
    db.query(SlackAlertLog).filter(
        SlackAlertLog.feedback_id.in_(feedback_ids)
    ).update({SlackAlertLog.feedback_id: None}, synchronize_session=False)

    # Delete all feedback items that belong to the current organization
    deleted_count = db.query(FeedbackItem).filter(
        FeedbackItem.id.in_(feedback_ids),
        FeedbackItem.organization_id == current_org.id
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "deleted_count": deleted_count,
        "message": f"Successfully deleted {deleted_count} feedback items"
    }


@router.patch("/{feedback_id}", response_model=FeedbackResponse)
def update_feedback(
    feedback_id: int,
    data: FeedbackCreateRequest,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Update a feedback item and re-analyze it."""

    feedback = db.query(FeedbackItem).filter(
        FeedbackItem.id == feedback_id,
        FeedbackItem.organization_id == current_org.id  # Multi-tenant isolation
    ).first()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found"
        )

    feedback.text = data.text
    if data.source is not None:
        feedback.source = data.source

    # Clear existing analysis
    feedback.sentiment_score = None
    feedback.sentiment_label = None
    feedback.extracted_issue = None
    feedback.is_urgent = False
    # Clear categorization fields
    feedback.pain_point_category = None
    feedback.pain_point_severity = None
    feedback.pain_point_text = None
    feedback.feature_request_category = None
    feedback.feature_request_priority = None
    feedback.feature_request_text = None
    feedback.urgent_category = None
    feedback.urgent_response_time = None
    feedback.categorization_confidence = None

    db.commit()

    # Re-analyze the feedback
    analyze_single_feedback(feedback, db)
    db.refresh(feedback)

    return feedback


@router.post("/import-csv", response_model=CSVImportResponse)
async def import_csv(
    file: UploadFile = File(...),
    current_org: Organization = Depends(get_current_org),
    usage: UsageRecord = Depends(get_current_usage),
    db: Session = Depends(get_db)
):
    """
    Import feedback from a CSV file.

    The CSV can have any schema, but it should contain at least one column with feedback text.
    Common column names detected: feedback_text, text, feedback, comment, message, description
    Optional columns: source, customer_email, date, rating
    """
    from src.config.plans import get_plan, get_feedback_limit

    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )

    # Check plan limits before importing
    plan = current_org.plan or "free"
    plan_config = get_plan(plan)
    limit = get_feedback_limit(plan)
    total_used = usage.feedback_count + usage.overage_feedback

    # For free plan, check if there's remaining capacity
    if limit is not None and not plan_config.get("overage_enabled") and total_used >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "feedback_limit_exceeded",
                "limit": limit,
                "used": total_used,
                "message": f"You've reached your monthly limit of {limit} feedback items. Upgrade to continue.",
                "upgrade_url": "/settings/billing"
            }
        )

    # Read CSV file
    contents = await file.read()
    decoded = contents.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(decoded))

    # Try to detect the feedback text column
    if not csv_reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty or invalid"
        )

    # Detect feedback text column (case-insensitive)
    text_column = None
    possible_text_columns = ['feedback_text', 'text', 'feedback', 'comment', 'message', 'description', 'review']
    fieldnames_lower = {name.lower(): name for name in csv_reader.fieldnames}

    for col in possible_text_columns:
        if col in fieldnames_lower:
            text_column = fieldnames_lower[col]
            break

    if not text_column:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not detect feedback text column. Please use one of: {', '.join(possible_text_columns)}"
        )

    # Detect optional columns
    source_column = None
    for col in ['source', 'channel', 'origin']:
        if col in fieldnames_lower:
            source_column = fieldnames_lower[col]
            break

    # Import feedback items
    total_rows = 0
    imported_count = 0
    failed_count = 0
    errors = []

    for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
        total_rows += 1

        try:
            # Get feedback text
            feedback_text = row.get(text_column, '').strip()

            if not feedback_text:
                errors.append(f"Row {row_num}: Empty feedback text")
                failed_count += 1
                continue

            # Get source (default to 'csv_import')
            source = 'csv_import'
            if source_column and row.get(source_column):
                source = row.get(source_column).strip()

            # Check if we can still import (for free plan)
            if limit is not None and not plan_config.get("overage_enabled"):
                if total_used + imported_count >= limit:
                    errors.append(f"Row {row_num}: Feedback limit reached ({limit})")
                    failed_count += 1
                    continue

            # Create feedback item
            feedback = FeedbackItem(
                organization_id=current_org.id,
                text=feedback_text,
                source=source
            )

            db.add(feedback)
            db.commit()
            db.refresh(feedback)

            # Track usage
            if limit is None:
                usage.feedback_count += 1
            elif usage.feedback_count < limit:
                usage.feedback_count += 1
            else:
                usage.overage_feedback += 1

            # Note: Analysis will be done by background scheduler
            imported_count += 1

        except Exception as e:
            failed_count += 1
            errors.append(f"Row {row_num}: {str(e)}")
            db.rollback()
            continue

    # Commit final usage tracking
    db.commit()

    # Queue batch analysis via Celery worker
    from src.background import queue_analyze_batch

    if imported_count > 0:
        # Get IDs of newly imported feedback items
        recent_feedback = db.query(FeedbackItem.id).filter(
            FeedbackItem.organization_id == current_org.id,
            FeedbackItem.sentiment_label == None,
            FeedbackItem.source == 'csv_import'
        ).order_by(FeedbackItem.created_at.desc()).limit(imported_count).all()

        feedback_ids = [f.id for f in recent_feedback]
        if feedback_ids:
            queue_analyze_batch(current_org.id, feedback_ids)

    return CSVImportResponse(
        total_rows=total_rows,
        imported_count=imported_count,
        failed_count=failed_count,
        errors=errors[:10]  # Limit to first 10 errors
    )
