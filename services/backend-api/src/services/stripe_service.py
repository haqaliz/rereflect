"""
Stripe service for handling billing operations.
"""
import os
from typing import Optional
from datetime import datetime

import stripe

from src.config.plans import get_plan, get_stripe_price_id


class StripeService:
    """Service for interacting with Stripe API."""

    def __init__(self):
        self.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        stripe.api_key = self.api_key

    def create_customer(
        self,
        email: str,
        name: str,
        organization_id: int,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Create a Stripe customer for an organization.

        Returns the Stripe customer ID.
        """
        customer_metadata = {
            "organization_id": str(organization_id),
            **(metadata or {}),
        }

        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata=customer_metadata,
        )

        return customer.id

    def create_checkout_session(
        self,
        customer_id: str,
        plan: str,
        billing_cycle: str,
        success_url: str,
        cancel_url: str,
        trial_days: Optional[int] = None,
    ) -> str:
        """
        Create a Stripe Checkout session for subscription.

        Returns the checkout session URL.
        """
        price_id = get_stripe_price_id(plan, billing_cycle)

        if not price_id:
            raise ValueError(f"No Stripe price configured for plan '{plan}' with cycle '{billing_cycle}'")

        session_params = {
            "customer": customer_id,
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": True,
            "billing_address_collection": "required",
        }

        # Add trial if specified
        if trial_days and trial_days > 0:
            session_params["subscription_data"] = {
                "trial_period_days": trial_days,
            }

        session = stripe.checkout.Session.create(**session_params)
        return session.url

    def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> str:
        """
        Create a Stripe Customer Portal session.

        Returns the portal session URL.
        """
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    def get_subscription(self, subscription_id: str) -> Optional[dict]:
        """Get subscription details from Stripe."""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "canceled_at": datetime.fromtimestamp(subscription.canceled_at) if subscription.canceled_at else None,
                "trial_start": datetime.fromtimestamp(subscription.trial_start) if subscription.trial_start else None,
                "trial_end": datetime.fromtimestamp(subscription.trial_end) if subscription.trial_end else None,
                "price_id": subscription["items"]["data"][0]["price"]["id"] if subscription["items"]["data"] else None,
            }
        except stripe.error.StripeError:
            return None

    def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
    ) -> bool:
        """
        Cancel a subscription.

        If at_period_end is True, subscription remains active until the end of the billing period.
        """
        try:
            if at_period_end:
                stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                )
            else:
                stripe.Subscription.cancel(subscription_id)
            return True
        except stripe.error.StripeError:
            return False

    def reactivate_subscription(self, subscription_id: str) -> bool:
        """Reactivate a subscription that was set to cancel at period end."""
        try:
            stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=False,
            )
            return True
        except stripe.error.StripeError:
            return False

    def update_subscription(
        self,
        subscription_id: str,
        new_price_id: str,
        proration_behavior: str = "create_prorations",
    ) -> bool:
        """
        Update subscription to a new plan/price.

        proration_behavior options:
        - "create_prorations": Prorate charges (default)
        - "none": No proration
        - "always_invoice": Invoice immediately
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            item_id = subscription["items"]["data"][0]["id"]

            stripe.Subscription.modify(
                subscription_id,
                items=[
                    {
                        "id": item_id,
                        "price": new_price_id,
                    }
                ],
                proration_behavior=proration_behavior,
            )
            return True
        except stripe.error.StripeError:
            return False

    def report_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: Optional[int] = None,
    ) -> bool:
        """
        Report metered usage to Stripe for overage billing.

        This is used for pay-as-you-go overage charges.
        """
        try:
            stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=quantity,
                timestamp=timestamp or int(datetime.utcnow().timestamp()),
                action="increment",
            )
            return True
        except stripe.error.StripeError:
            return False

    def get_invoices(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get list of invoices for a customer."""
        try:
            invoices = stripe.Invoice.list(
                customer=customer_id,
                limit=limit,
            )
            return [
                {
                    "id": inv.id,
                    "number": inv.number,
                    "amount_due": inv.amount_due,
                    "amount_paid": inv.amount_paid,
                    "currency": inv.currency,
                    "status": inv.status,
                    "created": datetime.fromtimestamp(inv.created),
                    "due_date": datetime.fromtimestamp(inv.due_date) if inv.due_date else None,
                    "paid_at": datetime.fromtimestamp(inv.status_transitions.paid_at) if inv.status_transitions.paid_at else None,
                    "hosted_invoice_url": inv.hosted_invoice_url,
                    "invoice_pdf": inv.invoice_pdf,
                }
                for inv in invoices.data
            ]
        except stripe.error.StripeError:
            return []

    def get_upcoming_invoice(self, customer_id: str) -> Optional[dict]:
        """Get upcoming invoice preview for a customer."""
        try:
            invoice = stripe.Invoice.upcoming(customer=customer_id)
            return {
                "amount_due": invoice.amount_due,
                "currency": invoice.currency,
                "period_start": datetime.fromtimestamp(invoice.period_start),
                "period_end": datetime.fromtimestamp(invoice.period_end),
                "lines": [
                    {
                        "description": line.description,
                        "amount": line.amount,
                        "quantity": line.quantity,
                    }
                    for line in invoice.lines.data
                ],
            }
        except stripe.error.StripeError:
            return None

    def manage_retention_addon(
        self,
        subscription_id: str,
        extra_days: int,
    ) -> bool:
        """
        Manage the notification retention add-on for a subscription.

        - extra_days > 0: Add or update the retention add-on subscription item
        - extra_days == 0: Remove the retention add-on if it exists

        Each unit = 1 extra day beyond the free 30-day baseline.
        Monthly cost = extra_days * $0.10 (configured in Stripe Price).
        """
        from src.config.plans import STRIPE_PRICE_RETENTION_ADDON

        if not STRIPE_PRICE_RETENTION_ADDON:
            return False

        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            items = subscription["items"]["data"]

            # Find existing retention add-on item
            addon_item = None
            for item in items:
                if item["price"]["id"] == STRIPE_PRICE_RETENTION_ADDON:
                    addon_item = item
                    break

            if extra_days > 0:
                if addon_item:
                    stripe.SubscriptionItem.modify(
                        addon_item["id"],
                        quantity=extra_days,
                    )
                else:
                    stripe.SubscriptionItem.create(
                        subscription=subscription_id,
                        price=STRIPE_PRICE_RETENTION_ADDON,
                        quantity=extra_days,
                    )
            elif addon_item:
                stripe.SubscriptionItem.delete(
                    addon_item["id"],
                    proration_behavior="create_prorations",
                )

            return True
        except stripe.error.StripeError as e:
            import logging
            logging.getLogger(__name__).error(f"Retention addon error: {e}")
            return False

    def verify_webhook_signature(
        self,
        payload: bytes,
        sig_header: str,
    ) -> Optional[dict]:
        """
        Verify Stripe webhook signature and return the event.

        Returns None if verification fails.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                self.webhook_secret,
            )
            return event
        except (ValueError, stripe.error.SignatureVerificationError):
            return None


# Singleton instance
_stripe_service: Optional[StripeService] = None


def get_stripe_service() -> StripeService:
    """Get or create the Stripe service singleton."""
    global _stripe_service
    if _stripe_service is None:
        _stripe_service = StripeService()
    return _stripe_service
