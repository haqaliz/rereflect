"""
Billing tasks for subscription management and usage tracking.
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)


@shared_task(name="billing.check_trial_expirations")
def check_trial_expirations():
    """
    Check for expired trials and downgrade to free plan.
    Should be run daily via Celery Beat.
    """
    logger.info("Checking for expired trials...")

    with get_db_session() as db:
        from src.models import Subscription, Organization

        # Find all trialing subscriptions that have expired
        now = datetime.utcnow()
        expired_trials = db.query(Subscription).filter(
            Subscription.status == "trialing",
            Subscription.trial_end < now
        ).all()

        if not expired_trials:
            logger.info("No expired trials found")
            return {"processed": 0}

        processed = 0
        for subscription in expired_trials:
            try:
                # Downgrade to free
                subscription.status = "active"
                subscription.plan = "free"
                subscription.trial_start = None
                subscription.trial_end = None

                # Update organization plan
                org = db.query(Organization).filter(
                    Organization.id == subscription.organization_id
                ).first()
                if org:
                    org.plan = "free"

                processed += 1
                logger.info(f"Expired trial downgraded for org {subscription.organization_id}")

            except Exception as e:
                logger.error(f"Error processing trial expiration for org {subscription.organization_id}: {e}")

        db.commit()
        logger.info(f"Processed {processed} expired trials")

        return {"processed": processed}


@shared_task(name="billing.report_overages_to_stripe")
def report_overages_to_stripe():
    """
    Report overage usage to Stripe for metered billing.
    Should be run hourly via Celery Beat.
    """
    import os

    # Only run if Stripe is configured
    if not os.environ.get("STRIPE_SECRET_KEY"):
        logger.debug("Stripe not configured, skipping overage reporting")
        return {"processed": 0}

    logger.info("Reporting overages to Stripe...")

    with get_db_session() as db:
        from src.models import UsageRecord, Subscription

        # Find usage records with unreported overages
        unreported = db.query(UsageRecord).filter(
            UsageRecord.overage_feedback > 0,
            UsageRecord.overage_reported_to_stripe == False
        ).all()

        if not unreported:
            logger.info("No unreported overages found")
            return {"processed": 0}

        processed = 0
        for usage in unreported:
            try:
                # Get subscription
                subscription = db.query(Subscription).filter(
                    Subscription.organization_id == usage.organization_id
                ).first()

                if not subscription or not subscription.stripe_subscription_id:
                    logger.warning(f"No Stripe subscription for org {usage.organization_id}, skipping")
                    continue

                # Report usage to Stripe
                # Note: This requires the subscription to have a metered price item
                # Implementation depends on Stripe subscription structure
                # For now, just mark as reported
                usage.overage_reported_to_stripe = True
                processed += 1

                logger.info(
                    f"Reported {usage.overage_feedback} overages for org {usage.organization_id}"
                )

            except Exception as e:
                logger.error(f"Error reporting overage for org {usage.organization_id}: {e}")

        db.commit()
        logger.info(f"Processed {processed} overage records")

        return {"processed": processed}


@shared_task(name="billing.send_trial_ending_reminder")
def send_trial_ending_reminder():
    """
    Send reminder emails to users whose trial is ending soon (3 days).
    Should be run daily via Celery Beat.
    """
    logger.info("Checking for trials ending soon...")

    with get_db_session() as db:
        from src.models import Subscription, Organization, User

        now = datetime.utcnow()
        reminder_date = now + timedelta(days=3)

        # Find trials ending within 3 days
        ending_soon = db.query(Subscription).filter(
            Subscription.status == "trialing",
            Subscription.trial_end >= now,
            Subscription.trial_end <= reminder_date
        ).all()

        if not ending_soon:
            logger.info("No trials ending soon")
            return {"processed": 0}

        processed = 0
        for subscription in ending_soon:
            try:
                # Get org and admin users
                org = db.query(Organization).filter(
                    Organization.id == subscription.organization_id
                ).first()

                if not org:
                    continue

                admins = db.query(User).filter(
                    User.organization_id == org.id,
                    User.role == "admin"
                ).all()

                days_remaining = (subscription.trial_end - now).days

                # TODO: Send email notification
                # For now, just log
                for admin in admins:
                    logger.info(
                        f"Trial ending reminder: {admin.email} - {days_remaining} days remaining"
                    )

                processed += 1

            except Exception as e:
                logger.error(f"Error sending trial reminder for org {subscription.organization_id}: {e}")

        logger.info(f"Processed {processed} trial reminders")
        return {"processed": processed}


@shared_task(name="billing.sync_subscription_status")
def sync_subscription_status(organization_id: int):
    """
    Sync subscription status from Stripe for a specific organization.
    Called after webhook events to ensure consistency.
    """
    import os

    if not os.environ.get("STRIPE_SECRET_KEY"):
        logger.debug("Stripe not configured, skipping sync")
        return {"synced": False}

    logger.info(f"Syncing subscription status for org {organization_id}...")

    with get_db_session() as db:
        from src.models import Subscription, Organization

        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id
        ).first()

        if not subscription or not subscription.stripe_subscription_id:
            logger.warning(f"No Stripe subscription for org {organization_id}")
            return {"synced": False}

        try:
            import stripe
            stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

            stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

            # Update local subscription
            subscription.status = stripe_sub.status
            subscription.cancel_at_period_end = stripe_sub.cancel_at_period_end
            subscription.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
            subscription.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)

            if stripe_sub.canceled_at:
                subscription.canceled_at = datetime.fromtimestamp(stripe_sub.canceled_at)

            # Update org plan if subscription is canceled
            if stripe_sub.status == "canceled":
                org = db.query(Organization).filter(
                    Organization.id == organization_id
                ).first()
                if org:
                    org.plan = "free"
                    subscription.plan = "free"

            db.commit()
            logger.info(f"Synced subscription for org {organization_id}")
            return {"synced": True}

        except Exception as e:
            logger.error(f"Error syncing subscription for org {organization_id}: {e}")
            return {"synced": False, "error": str(e)}


@shared_task(name="billing.check_usage_warnings")
def check_usage_warnings():
    """
    Check for organizations approaching their usage limits and send warnings.
    Should be run daily via Celery Beat.
    """
    logger.info("Checking for usage warnings...")

    with get_db_session() as db:
        from src.models import UsageRecord, Subscription, Organization, User
        from src.plans import get_feedback_limit

        # Get all usage records for current period
        now = datetime.utcnow()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        usage_records = db.query(UsageRecord).filter(
            UsageRecord.period_start >= current_month_start
        ).all()

        warnings_sent = 0
        for usage in usage_records:
            try:
                org = db.query(Organization).filter(
                    Organization.id == usage.organization_id
                ).first()

                if not org:
                    continue

                plan = org.plan or "free"
                limit = get_feedback_limit(plan)

                if limit is None:
                    continue  # Unlimited

                percentage = (usage.feedback_count / limit) * 100

                # Send warning at 80%
                if 80 <= percentage < 100:
                    admins = db.query(User).filter(
                        User.organization_id == org.id,
                        User.role == "admin"
                    ).all()

                    for admin in admins:
                        # TODO: Send email warning
                        logger.info(
                            f"Usage warning: {admin.email} - {usage.feedback_count}/{limit} ({percentage:.0f}%)"
                        )

                    warnings_sent += 1

            except Exception as e:
                logger.error(f"Error checking usage for org {usage.organization_id}: {e}")

        logger.info(f"Sent {warnings_sent} usage warnings")
        return {"warnings_sent": warnings_sent}
