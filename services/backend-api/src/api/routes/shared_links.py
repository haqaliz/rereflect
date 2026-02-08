"""
Shared links endpoints for public dashboard sharing.
Both authenticated (create/list/deactivate) and public (view) endpoints.
"""
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_, asc, desc
from pydantic import BaseModel, Field

from src.database.session import get_db
from src.models.shared_link import SharedLink
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.api.dependencies import get_current_user, get_current_org, require_feature
from src.api.auth import hash_password, verify_password

# ─── Authenticated routes ───────────────────────────────────────

router = APIRouter(prefix="/api/v1/shared-links", tags=["shared-links"])


class SharedLinkCreate(BaseModel):
    expiration: str = Field("7d", pattern="^(24h|7d|30d|never)$")
    password: Optional[str] = None


class SharedLinkResponse(BaseModel):
    id: int
    token: str
    page: str
    expires_at: Optional[datetime]
    is_active: bool
    view_count: int
    has_password: bool
    created_at: datetime

    class Config:
        from_attributes = True


EXPIRATION_MAP = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "never": None,
}


@router.post(
    "/",
    response_model=SharedLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("dashboard_sharing"))],
)
def create_shared_link(
    data: SharedLinkCreate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new shared analytics link."""
    delta = EXPIRATION_MAP.get(data.expiration)
    expires_at = (datetime.utcnow() + delta) if delta else None

    pwd_hash = hash_password(data.password) if data.password else None

    link = SharedLink.create(
        organization_id=current_org.id,
        page="analytics",
        created_by_id=current_user.id,
        password_hash=pwd_hash,
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return _to_response(link)


@router.get("/", response_model=List[SharedLinkResponse])
def list_shared_links(
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List active shared links for the organization."""
    links = (
        db.query(SharedLink)
        .filter(SharedLink.organization_id == current_org.id, SharedLink.is_active == True)
        .order_by(SharedLink.created_at.desc())
        .all()
    )
    return [_to_response(l) for l in links]


class PaginatedSharedLinksResponse(BaseModel):
    items: List[SharedLinkResponse]
    total: int
    page: int
    page_size: int


@router.get("/all", response_model=PaginatedSharedLinksResponse)
def list_all_shared_links(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|expired|deactivated)$"),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("desc"),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all shared links (active + expired + deactivated) with filtering and pagination."""
    q = db.query(SharedLink).filter(SharedLink.organization_id == current_org.id)

    # Status filter
    now = datetime.utcnow()
    if status_filter == "active":
        q = q.filter(
            SharedLink.is_active == True,
            or_(SharedLink.expires_at.is_(None), SharedLink.expires_at > now),
        )
    elif status_filter == "expired":
        q = q.filter(SharedLink.expires_at.isnot(None), SharedLink.expires_at <= now)
    elif status_filter == "deactivated":
        q = q.filter(SharedLink.is_active == False)

    # Search by token suffix
    if search:
        q = q.filter(SharedLink.token.ilike(f"%{search}%"))

    # Date range filter
    if date_from:
        try:
            q = q.filter(SharedLink.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(SharedLink.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    total = q.count()

    sort_map = {
        "created_at": SharedLink.created_at,
        "view_count": SharedLink.view_count,
        "expires_at": SharedLink.expires_at,
    }
    sort_col = sort_map.get(sort_by, SharedLink.created_at)
    order_fn = asc if sort_order == "asc" else desc
    links = q.order_by(order_fn(sort_col)).offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedSharedLinksResponse(
        items=[_to_response(l) for l in links],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_shared_link(
    link_id: int,
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Deactivate a shared link."""
    link = (
        db.query(SharedLink)
        .filter(SharedLink.id == link_id, SharedLink.organization_id == current_org.id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Shared link not found")

    link.is_active = False
    db.commit()


def _to_response(link: SharedLink) -> SharedLinkResponse:
    return SharedLinkResponse(
        id=link.id,
        token=link.token,
        page=link.page,
        expires_at=link.expires_at,
        is_active=link.is_active,
        view_count=link.view_count,
        has_password=link.password_hash is not None,
        created_at=link.created_at,
    )


# ─── Public routes (no auth) ───────────────────────────────────

public_router = APIRouter(prefix="/api/v1/public", tags=["public"])


class PublicAnalyticsResponse(BaseModel):
    requires_password: bool = False
    org_name: Optional[str] = None
    data: Optional[dict] = None


class PasswordVerifyRequest(BaseModel):
    password: str


@public_router.get("/analytics/{token}")
def get_public_analytics(token: str, db: Session = Depends(get_db)):
    """Get public analytics data by shared link token."""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()

    if not link or not link.is_valid():
        raise HTTPException(status_code=410, detail="This link has expired or been deactivated")

    org = db.query(Organization).filter(Organization.id == link.organization_id).first()

    # If password-protected, require verification first
    if link.password_hash:
        return PublicAnalyticsResponse(requires_password=True, org_name=org.name if org else None)

    # Increment view count
    link.view_count += 1
    db.commit()

    data = _build_public_analytics(db, link.organization_id)
    return PublicAnalyticsResponse(
        requires_password=False,
        org_name=org.name if org else None,
        data=data,
    )


@public_router.post("/analytics/{token}/verify")
def verify_and_get_analytics(
    token: str,
    body: PasswordVerifyRequest,
    db: Session = Depends(get_db),
):
    """Verify password and return analytics data."""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()

    if not link or not link.is_valid():
        raise HTTPException(status_code=410, detail="This link has expired or been deactivated")

    if not link.password_hash or not verify_password(body.password, link.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Increment view count
    link.view_count += 1
    db.commit()

    org = db.query(Organization).filter(Organization.id == link.organization_id).first()
    data = _build_public_analytics(db, link.organization_id)

    return PublicAnalyticsResponse(
        requires_password=False,
        org_name=org.name if org else None,
        data=data,
    )


def _compute_trend(first_half_count: int, second_half_count: int) -> str:
    """Compare second half vs first half — >10% diff = up/down."""
    if first_half_count == 0 and second_half_count == 0:
        return "stable"
    if first_half_count == 0:
        return "up"
    ratio = (second_half_count - first_half_count) / first_half_count
    if ratio > 0.10:
        return "up"
    elif ratio < -0.10:
        return "down"
    return "stable"


def _build_public_analytics(db: Session, org_id: int) -> dict:
    """Build analytics data for public view (last 30 days)."""
    start_date = datetime.utcnow() - timedelta(days=30)
    mid_date = datetime.utcnow() - timedelta(days=15)

    base_q = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.created_at >= start_date,
    )

    total = base_q.count()

    # Sentiment distribution
    sent = base_q.with_entities(
        func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("pos"),
        func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neu"),
        func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("neg"),
    ).first()

    # Source distribution
    src_rows = (
        base_q.with_entities(FeedbackItem.source, func.count(FeedbackItem.id).label("cnt"))
        .group_by(FeedbackItem.source)
        .order_by(func.count(FeedbackItem.id).desc())
        .all()
    )

    # Daily time series (with all metric fields)
    trunc_expr = func.date_trunc("day", FeedbackItem.created_at)
    ts_rows = (
        base_q.with_entities(
            trunc_expr.label("bucket"),
            func.count(FeedbackItem.id).label("cnt"),
            func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
            func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("pos"),
            func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neu"),
            func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("neg"),
            func.sum(case((FeedbackItem.is_urgent == True, 1), else_=0)).label("urg"),
            func.sum(case((FeedbackItem.pain_point_category.isnot(None), 1), else_=0)).label("pp"),
            func.sum(case((FeedbackItem.feature_request_category.isnot(None), 1), else_=0)).label("fr"),
        )
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    # Top pain points (top 10)
    pp_rows = (
        base_q.filter(FeedbackItem.pain_point_category.isnot(None))
        .with_entities(
            FeedbackItem.pain_point_category.label("name"),
            func.count(FeedbackItem.id).label("cnt"),
            func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
        )
        .group_by(FeedbackItem.pain_point_category)
        .order_by(func.count(FeedbackItem.id).desc())
        .limit(10)
        .all()
    )

    top_pain_points = []
    for row in pp_rows:
        first_half = base_q.filter(
            FeedbackItem.pain_point_category == row.name,
            FeedbackItem.created_at < mid_date,
        ).count()
        second_half = int(row.cnt) - first_half
        top_pain_points.append({
            "name": row.name,
            "count": int(row.cnt),
            "trend": _compute_trend(first_half, second_half),
            "avg_sentiment": round(float(row.avg_sent), 3) if row.avg_sent is not None else None,
        })

    # Top feature requests (top 10)
    fr_rows = (
        base_q.filter(FeedbackItem.feature_request_category.isnot(None))
        .with_entities(
            FeedbackItem.feature_request_category.label("name"),
            func.count(FeedbackItem.id).label("cnt"),
            func.avg(FeedbackItem.sentiment_score).label("avg_sent"),
        )
        .group_by(FeedbackItem.feature_request_category)
        .order_by(func.count(FeedbackItem.id).desc())
        .limit(10)
        .all()
    )

    top_feature_requests = []
    for row in fr_rows:
        first_half = base_q.filter(
            FeedbackItem.feature_request_category == row.name,
            FeedbackItem.created_at < mid_date,
        ).count()
        second_half = int(row.cnt) - first_half
        top_feature_requests.append({
            "name": row.name,
            "count": int(row.cnt),
            "trend": _compute_trend(first_half, second_half),
            "avg_sentiment": round(float(row.avg_sent), 3) if row.avg_sent is not None else None,
        })

    def _fmt_bucket(b):
        if b is None:
            return ""
        return b[:10] if isinstance(b, str) else b.strftime("%Y-%m-%d")

    return {
        "total_feedback": total,
        "date_range": "Last 30 days",
        "granularity": "daily",
        "sentiment_distribution": {
            "positive": int(sent.pos or 0) if sent else 0,
            "neutral": int(sent.neu or 0) if sent else 0,
            "negative": int(sent.neg or 0) if sent else 0,
        },
        "source_distribution": [
            {"source": r.source or "unknown", "count": int(r.cnt), "percentage": round(int(r.cnt) / total * 100, 1) if total else 0}
            for r in src_rows
        ],
        "data_points": [
            {
                "date": _fmt_bucket(r.bucket),
                "feedback_count": int(r.cnt),
                "avg_sentiment_score": round(float(r.avg_sent), 3) if r.avg_sent else None,
                "positive_count": int(r.pos or 0),
                "neutral_count": int(r.neu or 0),
                "negative_count": int(r.neg or 0),
                "urgent_count": int(r.urg or 0),
                "pain_points_count": int(r.pp or 0),
                "feature_requests_count": int(r.fr or 0),
            }
            for r in ts_rows
        ],
        "top_pain_points": top_pain_points,
        "top_feature_requests": top_feature_requests,
    }
