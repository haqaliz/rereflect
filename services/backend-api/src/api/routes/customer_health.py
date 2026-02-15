from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.api.dependencies import get_current_org, require_feature

router = APIRouter(prefix="/api/v1/customer-health", tags=["customer-health"])


class CustomerHealthResponse(BaseModel):
    customer_email: str
    customer_name: Optional[str] = None
    health_score: int
    risk_level: str
    churn_risk_component: int
    sentiment_component: int
    resolution_component: int
    frequency_component: int
    feedback_count: int
    last_feedback_at: Optional[datetime] = None
    llm_analysis: Optional[str] = None
    llm_analyzed_at: Optional[datetime] = None


@router.get(
    "/{email}",
    response_model=CustomerHealthResponse,
    dependencies=[Depends(require_feature("customer_health_scores"))],
)
def get_customer_health(
    email: str,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get health score data for a specific customer by email."""
    record = db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == current_org.id,
        CustomerHealth.customer_email == email,
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health record found for customer '{email}'",
        )

    return CustomerHealthResponse(
        customer_email=record.customer_email,
        customer_name=record.customer_name,
        health_score=record.health_score,
        risk_level=record.risk_level,
        churn_risk_component=record.churn_risk_component,
        sentiment_component=record.sentiment_component,
        resolution_component=record.resolution_component,
        frequency_component=record.frequency_component,
        feedback_count=record.feedback_count,
        last_feedback_at=record.last_feedback_at,
        llm_analysis=record.llm_analysis,
        llm_analyzed_at=record.llm_analyzed_at,
    )
