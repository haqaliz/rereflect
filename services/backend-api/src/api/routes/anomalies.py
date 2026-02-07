"""
Anomaly detection API endpoints.
Provides listing and resolution of sentiment anomalies.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.models.anomaly import SentimentAnomaly
from src.models.organization import Organization
from src.api.dependencies import get_current_org

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])


# Schemas
class AnomalyResponse(BaseModel):
    id: int
    organization_id: int
    detected_at: datetime
    anomaly_type: str
    severity: str
    baseline_negative_pct: float
    current_negative_pct: float
    deviation_pct: float
    time_window_hours: int
    feedback_count: int
    is_resolved: bool
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AnomalyListResponse(BaseModel):
    items: List[AnomalyResponse]
    total: int


# Endpoints
@router.get("/", response_model=AnomalyListResponse)
def list_anomalies(
    is_resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    severity: Optional[str] = Query(None, description="Filter by severity (warning, critical)"),
    limit: int = Query(20, ge=1, le=100),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List sentiment anomalies for the current organization."""
    query = db.query(SentimentAnomaly).filter(
        SentimentAnomaly.organization_id == current_org.id,
    )

    if is_resolved is not None:
        query = query.filter(SentimentAnomaly.is_resolved == is_resolved)

    if severity:
        query = query.filter(SentimentAnomaly.severity == severity)

    total = query.count()
    items = query.order_by(SentimentAnomaly.detected_at.desc()).limit(limit).all()

    return AnomalyListResponse(
        items=[AnomalyResponse.model_validate(item) for item in items],
        total=total,
    )


@router.patch("/{anomaly_id}/resolve", response_model=AnomalyResponse)
def resolve_anomaly(
    anomaly_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Mark an anomaly as resolved."""
    anomaly = db.query(SentimentAnomaly).filter(
        SentimentAnomaly.id == anomaly_id,
        SentimentAnomaly.organization_id == current_org.id,
    ).first()

    if not anomaly:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomaly not found",
        )

    if anomaly.is_resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anomaly is already resolved",
        )

    anomaly.is_resolved = True
    anomaly.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(anomaly)

    return AnomalyResponse.model_validate(anomaly)
