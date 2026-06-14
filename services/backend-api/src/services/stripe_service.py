"""
Stripe service for handling billing operations.

SELF-HOSTED OSS NOTE (B3):
Stripe is stripped from the self-hosted product. This module is kept as a
stub so that existing imports (e.g., from admin_promo or tests that stub it)
do not cause ImportError. The `stripe` package itself is optional — we
guard the import so the app boots even when `stripe` is not installed.
All real Stripe calls are no-ops in the stub class below.
"""
import os
from typing import Optional
from datetime import datetime

# Import guard: app must boot even if the `stripe` package is absent.
try:
    import stripe as _stripe_pkg
    _STRIPE_AVAILABLE = True
except (ImportError, TypeError):
    _stripe_pkg = None  # type: ignore[assignment]
    _STRIPE_AVAILABLE = False

from src.config.plans import get_plan, get_stripe_price_id


class StripeService:
    """
    Stub Stripe service.  All methods are no-ops / raise gracefully when
    `stripe` is unavailable, so the app continues to run.
    """

    def __init__(self):
        self.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if _STRIPE_AVAILABLE and _stripe_pkg is not None:
            _stripe_pkg.api_key = self.api_key

    # ── All methods below are kept as stubs so existing imports compile. ──────

    def create_customer(self, email: str, name: str, organization_id: int,
                        metadata: Optional[dict] = None) -> str:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            raise RuntimeError("Stripe package not installed")
        customer_metadata = {"organization_id": str(organization_id), **(metadata or {})}
        customer = _stripe_pkg.Customer.create(email=email, name=name, metadata=customer_metadata)
        return customer.id

    def create_checkout_session(self, customer_id: str, plan: str, billing_cycle: str,
                                success_url: str, cancel_url: str,
                                trial_days: Optional[int] = None,
                                promo_code: Optional[str] = None) -> str:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            raise RuntimeError("Stripe package not installed")
        price_id = get_stripe_price_id(plan, billing_cycle)
        if not price_id:
            raise ValueError(f"No Stripe price configured for plan '{plan}' with cycle '{billing_cycle}'")
        session_params: dict = {
            "customer": customer_id, "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "mode": "subscription", "success_url": success_url,
            "cancel_url": cancel_url, "allow_promotion_codes": True,
            "billing_address_collection": "required",
        }
        if promo_code:
            promo_codes = _stripe_pkg.PromotionCode.list(code=promo_code, active=True, limit=1)
            if promo_codes.data:
                session_params["discounts"] = [{"promotion_code": promo_codes.data[0].id}]
                session_params.pop("allow_promotion_codes", None)
                session_params["payment_method_collection"] = "if_required"
        if trial_days and trial_days > 0:
            session_params["subscription_data"] = {"trial_period_days": trial_days}
        session = _stripe_pkg.checkout.Session.create(**session_params)
        return session.url

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            raise RuntimeError("Stripe package not installed")
        session = _stripe_pkg.billing_portal.Session.create(customer=customer_id, return_url=return_url)
        return session.url

    def get_subscription(self, subscription_id: str) -> Optional[dict]:
        """No-op in self-hosted mode (B3/B4 — Stripe stripped)."""
        return None

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return False
        try:
            if at_period_end:
                _stripe_pkg.Subscription.modify(subscription_id, cancel_at_period_end=True)
            else:
                _stripe_pkg.Subscription.cancel(subscription_id)
            return True
        except Exception:
            return False

    def reactivate_subscription(self, subscription_id: str) -> bool:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return False
        try:
            _stripe_pkg.Subscription.modify(subscription_id, cancel_at_period_end=False)
            return True
        except Exception:
            return False

    def update_subscription(self, subscription_id: str, new_price_id: str,
                            proration_behavior: str = "create_prorations") -> bool:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return False
        try:
            subscription = _stripe_pkg.Subscription.retrieve(subscription_id)
            item_id = subscription["items"]["data"][0]["id"]
            _stripe_pkg.Subscription.modify(
                subscription_id,
                items=[{"id": item_id, "price": new_price_id}],
                proration_behavior=proration_behavior,
            )
            return True
        except Exception:
            return False

    def report_usage(self, subscription_item_id: str, quantity: int,
                     timestamp: Optional[int] = None) -> bool:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return False
        try:
            _stripe_pkg.SubscriptionItem.create_usage_record(
                subscription_item_id, quantity=quantity,
                timestamp=timestamp or int(datetime.utcnow().timestamp()),
                action="increment",
            )
            return True
        except Exception:
            return False

    def get_invoices(self, customer_id: str, limit: int = 10) -> list:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return []
        try:
            invoices = _stripe_pkg.Invoice.list(customer=customer_id, limit=limit)
            return [
                {
                    "id": inv.id, "number": inv.number,
                    "amount_due": inv.amount_due, "amount_paid": inv.amount_paid,
                    "currency": inv.currency, "status": inv.status,
                    "created": datetime.fromtimestamp(inv.created),
                    "due_date": datetime.fromtimestamp(inv.due_date) if inv.due_date else None,
                    "paid_at": datetime.fromtimestamp(inv.status_transitions.paid_at) if inv.status_transitions.paid_at else None,
                    "hosted_invoice_url": inv.hosted_invoice_url,
                    "invoice_pdf": inv.invoice_pdf,
                }
                for inv in invoices.data
            ]
        except Exception:
            return []

    def get_upcoming_invoice(self, customer_id: str) -> Optional[dict]:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return None
        try:
            invoice = _stripe_pkg.Invoice.upcoming(customer=customer_id)
            return {
                "amount_due": invoice.amount_due, "currency": invoice.currency,
                "period_start": datetime.fromtimestamp(invoice.period_start),
                "period_end": datetime.fromtimestamp(invoice.period_end),
                "lines": [
                    {"description": line.description, "amount": line.amount, "quantity": line.quantity}
                    for line in invoice.lines.data
                ],
            }
        except Exception:
            return None

    def manage_retention_addon(self, subscription_id: str, extra_days: int) -> bool:
        """No-op in self-hosted mode (B3 — Stripe stripped)."""
        return False

    def list_promotion_codes(self, limit: int = 50, active: Optional[bool] = None) -> list:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return []
        params: dict = {"limit": limit, "expand": ["data.coupon"]}
        if active is not None:
            params["active"] = active
        result = _stripe_pkg.PromotionCode.list(**params)
        return result.data

    def get_promotion_code(self, promo_code_id: str):
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return None
        try:
            return _stripe_pkg.PromotionCode.retrieve(promo_code_id, expand=["coupon"])
        except Exception:
            return None

    def create_coupon_and_promo(self, coupon_params: dict, promo_params: dict):
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            raise RuntimeError("Stripe package not installed")
        coupon = _stripe_pkg.Coupon.create(**coupon_params)
        promo = _stripe_pkg.PromotionCode.create(coupon=coupon.id, **promo_params)
        return promo

    def deactivate_promotion_code(self, promo_code_id: str) -> bool:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return False
        try:
            _stripe_pkg.PromotionCode.modify(promo_code_id, active=False)
            return True
        except Exception:
            return False

    def delete_promotion_code(self, promo_code_id: str, coupon_id: str) -> bool:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return False
        try:
            _stripe_pkg.PromotionCode.modify(promo_code_id, active=False)
        except Exception:
            return False
        try:
            _stripe_pkg.Coupon.delete(coupon_id)
        except Exception:
            pass
        return True

    def verify_webhook_signature(self, payload: bytes, sig_header: str) -> Optional[dict]:
        if not _STRIPE_AVAILABLE or _stripe_pkg is None:
            return None
        try:
            event = _stripe_pkg.Webhook.construct_event(payload, sig_header, self.webhook_secret)
            return event
        except Exception:
            return None


# Singleton instance
_stripe_service: Optional[StripeService] = None


def get_stripe_service() -> StripeService:
    """Get or create the Stripe service singleton."""
    global _stripe_service
    if _stripe_service is None:
        _stripe_service = StripeService()
    return _stripe_service
