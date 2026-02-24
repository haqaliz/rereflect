"""
Copilot REST API supplementary endpoints (M2.2).

- GET /api/v1/copilot/usage — User's copilot usage stats
- POST /api/v1/conversations/suggestions — Dynamic query suggestions
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.api.dependencies import get_current_user, get_current_org
from src.services.copilot_rate_limiter import get_usage_stats

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class UsageResponse(BaseModel):
    plan: str
    daily_queries_used: int
    daily_queries_limit: Optional[int]  # None = unlimited
    monthly_tokens_used: int
    monthly_tokens_limit: Optional[int]  # None = unlimited


@router.get("/usage", response_model=UsageResponse)
def get_copilot_usage(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get current user's copilot usage statistics."""
    stats = get_usage_stats(current_user.id, current_org, db)
    return UsageResponse(**stats)
