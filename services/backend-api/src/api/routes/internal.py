"""Internal service-to-service endpoints.

Authenticated with a shared secret rather than a user JWT: the caller is another
Rereflect service (the Celery worker), not a browser. Fails closed when the
secret is not configured.
"""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.customer_health import CustomerHealth
from src.services.health_score_service import update_customer_health

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    secret = os.getenv("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Internal API is not configured")
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret, secret):
        raise HTTPException(status_code=403, detail="Invalid internal secret")


class HealthRecomputeRequest(BaseModel):
    org_id: int
    customer_email: str


@router.post("/health/recompute", dependencies=[Depends(require_internal_secret)])
def recompute_health(payload: HealthRecomputeRequest, db: Session = Depends(get_db)) -> dict:
    """Run the one real health-score implementation for one customer."""
    customer_email = payload.customer_email.strip()
    if not customer_email:
        raise HTTPException(status_code=422, detail="customer_email is required")

    update_customer_health(payload.org_id, customer_email, db)
    db.commit()

    row = (
        db.query(CustomerHealth)
        .filter_by(organization_id=payload.org_id, customer_email=customer_email)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Health score was not written")
    return {"status": "ok", "health_score": row.health_score}
