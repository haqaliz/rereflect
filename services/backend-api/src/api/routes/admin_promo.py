"""
Admin Promo Code management API endpoints.
All endpoints require system admin access.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database.session import get_db
from src.api.dependencies import require_system_admin
from src.services.stripe_service import get_stripe_service
from src.models.organization import Organization

router = APIRouter(prefix="/api/v1/admin/promo-codes", tags=["admin-promo"])


# Schemas

class CouponSummary(BaseModel):
    id: str
    name: Optional[str] = None
    percent_off: Optional[float] = None
    amount_off: Optional[int] = None
    currency: Optional[str] = None
    duration: str
    duration_in_months: Optional[int] = None


class PromoCodeResponse(BaseModel):
    id: str
    code: str
    active: bool
    coupon: CouponSummary
    max_redemptions: Optional[int] = None
    times_redeemed: int
    expires_at: Optional[datetime] = None
    created: datetime
    metadata: Optional[dict] = None


class PromoCodeListResponse(BaseModel):
    promo_codes: List[PromoCodeResponse]
    total: int


def _stripe_promo_to_response(promo) -> dict:
    """Convert a Stripe PromotionCode object to response dict."""
    coupon = promo["coupon"] if isinstance(promo, dict) else promo.coupon
    coupon_data = coupon if isinstance(coupon, dict) else {
        "id": coupon.id,
        "name": coupon.name,
        "percent_off": coupon.percent_off,
        "amount_off": coupon.amount_off,
        "currency": coupon.currency,
        "duration": coupon.duration,
        "duration_in_months": getattr(coupon, "duration_in_months", None),
    }

    p = promo if isinstance(promo, dict) else promo
    promo_id = p["id"] if isinstance(p, dict) else p.id
    code = p["code"] if isinstance(p, dict) else p.code
    active = p["active"] if isinstance(p, dict) else p.active
    max_redemptions = p["max_redemptions"] if isinstance(p, dict) else p.max_redemptions
    times_redeemed = p["times_redeemed"] if isinstance(p, dict) else p.times_redeemed
    expires_at_raw = p["expires_at"] if isinstance(p, dict) else p.expires_at
    created_raw = p["created"] if isinstance(p, dict) else p.created
    metadata = p.get("metadata") if isinstance(p, dict) else getattr(p, "metadata", None)

    return {
        "id": promo_id,
        "code": code,
        "active": active,
        "coupon": coupon_data,
        "max_redemptions": max_redemptions,
        "times_redeemed": times_redeemed,
        "expires_at": datetime.fromtimestamp(expires_at_raw) if expires_at_raw else None,
        "created": datetime.fromtimestamp(created_raw) if isinstance(created_raw, (int, float)) else created_raw,
        "metadata": metadata,
    }


# Endpoints

class PromoRedemption(BaseModel):
    organization_id: int
    organization_name: str
    redeemed_at: Optional[datetime] = None


class PromoCodeDetailResponse(PromoCodeResponse):
    customer: Optional[str] = None
    first_time_transaction: bool = False
    minimum_amount: Optional[int] = None
    minimum_amount_currency: Optional[str] = None
    redeemed_by: List[PromoRedemption] = []


@router.get("", response_model=PromoCodeListResponse, dependencies=[Depends(require_system_admin)])
def list_promo_codes():
    """List all promotion codes from Stripe."""
    service = get_stripe_service()
    promos = service.list_promotion_codes()
    items = [_stripe_promo_to_response(p) for p in promos]
    return PromoCodeListResponse(promo_codes=items, total=len(items))


@router.get("/{promo_code_id}", response_model=PromoCodeDetailResponse, dependencies=[Depends(require_system_admin)])
def get_promo_code_detail(
    promo_code_id: str,
    db: Session = Depends(get_db),
):
    """Get promo code detail from Stripe + local redemption data."""
    service = get_stripe_service()
    promo = service.get_promotion_code(promo_code_id)
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promotion code not found")

    base = _stripe_promo_to_response(promo)

    # Extract extra fields
    code = base["code"]
    restrictions = promo["restrictions"] if isinstance(promo, dict) else getattr(promo, "restrictions", {})
    if isinstance(restrictions, dict):
        first_time = restrictions.get("first_time_transaction", False)
        min_amount = restrictions.get("minimum_amount")
        min_currency = restrictions.get("minimum_amount_currency")
    else:
        first_time = getattr(restrictions, "first_time_transaction", False)
        min_amount = getattr(restrictions, "minimum_amount", None)
        min_currency = getattr(restrictions, "minimum_amount_currency", None)

    customer = promo["customer"] if isinstance(promo, dict) else getattr(promo, "customer", None)

    # Query local DB for orgs that used this promo code
    orgs = db.query(Organization).filter(Organization.promo_code_used == code).all()
    redeemed_by = [
        PromoRedemption(
            organization_id=org.id,
            organization_name=org.name,
            redeemed_at=org.created_at,
        )
        for org in orgs
    ]

    return PromoCodeDetailResponse(
        **base,
        customer=customer,
        first_time_transaction=first_time,
        minimum_amount=min_amount,
        minimum_amount_currency=min_currency,
        redeemed_by=redeemed_by,
    )


class CreatePromoRequest(BaseModel):
    code: str
    max_redemptions: Optional[int] = None
    first_time_transaction: bool = True
    expires_at: Optional[datetime] = None
    coupon_name: str
    discount_type: str  # "percent" or "amount"
    percent_off: Optional[float] = None
    amount_off: Optional[int] = None
    currency: str = "usd"
    duration: str  # "once", "repeating", "forever"
    duration_in_months: Optional[int] = None
    applies_to_prices: Optional[List[str]] = None


@router.post("", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_system_admin)])
def create_promo_code(request: CreatePromoRequest):
    """Create a coupon and promotion code in Stripe."""
    service = get_stripe_service()

    coupon_params = {
        "name": request.coupon_name,
        "duration": request.duration,
    }
    if request.discount_type == "percent":
        coupon_params["percent_off"] = request.percent_off
    else:
        coupon_params["amount_off"] = request.amount_off
        coupon_params["currency"] = request.currency

    if request.duration == "repeating" and request.duration_in_months:
        coupon_params["duration_in_months"] = request.duration_in_months

    if request.applies_to_prices:
        coupon_params["applies_to"] = {"products": request.applies_to_prices}

    promo_params = {
        "code": request.code,
    }
    if request.max_redemptions is not None:
        promo_params["max_redemptions"] = request.max_redemptions
    if request.first_time_transaction:
        promo_params["restrictions"] = {"first_time_transaction": True}
    if request.expires_at:
        promo_params["expires_at"] = int(request.expires_at.timestamp())

    promo = service.create_coupon_and_promo(coupon_params, promo_params)
    return _stripe_promo_to_response(promo)


@router.post("/{promo_code_id}/deactivate", dependencies=[Depends(require_system_admin)])
def deactivate_promo_code(promo_code_id: str):
    """Deactivate a promotion code in Stripe."""
    service = get_stripe_service()
    success = service.deactivate_promotion_code(promo_code_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promotion code not found or already inactive")
    return {"status": "deactivated"}


@router.delete("/{promo_code_id}", dependencies=[Depends(require_system_admin)])
def delete_promo_code(promo_code_id: str, coupon_id: str):
    """Delete a promotion code: deactivate in Stripe and delete its coupon."""
    service = get_stripe_service()
    success = service.delete_promotion_code(promo_code_id, coupon_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promotion code not found")
    return {"status": "deleted"}
