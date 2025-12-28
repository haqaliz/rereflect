from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import desc, cast, func
from sqlalchemy.dialects.postgresql import JSONB
from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.api.dependencies import get_current_org
from pydantic import BaseModel
from datetime import datetime
from typing import List
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


# Helper function for automatic analysis
def analyze_single_feedback(feedback: FeedbackItem, db: Session) -> None:
    """Automatically analyze a single feedback item."""
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

        db.commit()
    except Exception as e:
        # If analysis fails, just continue without analysis
        print(f"Auto-analysis failed: {str(e)}")
        pass


# Schemas
class FeedbackCreateRequest(BaseModel):
    text: str
    source: str | None = "manual"


class FeedbackResponse(BaseModel):
    id: int
    organization_id: int
    text: str
    source: str | None
    sentiment_score: float | None
    sentiment_label: str | None
    extracted_issue: str | None
    tags: list[str] | None
    is_urgent: bool
    created_at: datetime

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
    db: Session = Depends(get_db)
):
    """Create a new feedback item. Background job will analyze it automatically."""

    feedback = FeedbackItem(
        organization_id=current_org.id,
        text=data.text,
        source=data.source
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # Note: Analysis will be done by background scheduler within 30 seconds
    return feedback


@router.get("/", response_model=FeedbackListResponse)
def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sentiment: str | None = Query(None, description="Filter by sentiment: positive, neutral, negative"),
    source: str | None = Query(None, description="Filter by source"),
    is_urgent: bool | None = Query(None, description="Filter by urgent status"),
    tag: str | None = Query(None, description="Filter by tag"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """List feedback items with pagination and filters."""

    # Base query
    query = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == current_org.id
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

    # Get total count
    total = query.count()

    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get items
    items = query.order_by(desc(FeedbackItem.created_at)).offset(offset).limit(page_size).all()

    return FeedbackListResponse(
        items=items,
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

    return feedback


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

    db.commit()

    # Re-analyze the feedback
    analyze_single_feedback(feedback, db)
    db.refresh(feedback)

    return feedback


@router.post("/import-csv", response_model=CSVImportResponse)
async def import_csv(
    file: UploadFile = File(...),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """
    Import feedback from a CSV file.

    The CSV can have any schema, but it should contain at least one column with feedback text.
    Common column names detected: feedback_text, text, feedback, comment, message, description
    Optional columns: source, customer_email, date, rating
    """

    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
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

            # Create feedback item
            feedback = FeedbackItem(
                organization_id=current_org.id,
                text=feedback_text,
                source=source
            )

            db.add(feedback)
            db.commit()
            db.refresh(feedback)

            # Note: Analysis will be done by background scheduler
            imported_count += 1

        except Exception as e:
            failed_count += 1
            errors.append(f"Row {row_num}: {str(e)}")
            db.rollback()
            continue

    return CSVImportResponse(
        total_rows=total_rows,
        imported_count=imported_count,
        failed_count=failed_count,
        errors=errors[:10]  # Limit to first 10 errors
    )
