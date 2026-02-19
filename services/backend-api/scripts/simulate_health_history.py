"""
Simulate realistic weekly health score history for all customers.

Replaces the single-point backfill with a week-by-week simulation going back
to each customer's earliest feedback date, computing "as of" scores using the
same component functions and weights as the live service.

Run:
    cd services/backend-api && source venv/bin/activate && python scripts/simulate_health_history.py
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func
from src.database.session import SessionLocal
from src.models.customer_health import CustomerHealth
from src.models.customer_health_history import CustomerHealthHistory
from src.models.feedback import FeedbackItem
from src.services.health_score_service import (
    _compute_churn_component,
    _compute_sentiment_component,
    _compute_resolution_component,
    _compute_frequency_component,
)

WEIGHTS = {
    "churn_risk": 0.35,
    "sentiment": 0.25,
    "resolution": 0.25,
    "frequency": 0.15,
}

BATCH_SIZE = 100


def _risk_level(score: int) -> str:
    if score >= 70:
        return "healthy"
    elif score >= 50:
        return "moderate"
    elif score >= 30:
        return "at_risk"
    return "critical"


def _compute_score_as_of(db, org_id: int, customer_email: str, as_of: datetime) -> dict:
    """Compute all health components and weighted score as of a given date."""
    churn = _compute_churn_component(db, org_id, customer_email, as_of)
    sentiment = _compute_sentiment_component(db, org_id, customer_email, as_of)
    resolution = _compute_resolution_component(db, org_id, customer_email, as_of)
    frequency = _compute_frequency_component(db, org_id, customer_email, as_of)

    score = int(
        churn * WEIGHTS["churn_risk"] +
        sentiment * WEIGHTS["sentiment"] +
        resolution * WEIGHTS["resolution"] +
        frequency * WEIGHTS["frequency"]
    )
    score = max(0, min(100, score))

    return {
        "health_score": score,
        "churn_risk_component": churn,
        "sentiment_component": sentiment,
        "resolution_component": resolution,
        "frequency_component": frequency,
        "risk_level": _risk_level(score),
    }


def main():
    db = SessionLocal()
    try:
        # Step 1: Delete all existing history records
        deleted = db.query(CustomerHealthHistory).delete()
        db.commit()
        print(f"Deleted {deleted} existing history records")

        # Step 2: Load all CustomerHealth records
        customers = db.query(CustomerHealth).filter(
            CustomerHealth.is_archived == False,
        ).all()
        print(f"Found {len(customers)} active customers to simulate history for")

        now = datetime.utcnow()
        total_inserted = 0
        batch = []

        for idx, ch in enumerate(customers, 1):
            # Find earliest feedback date for this customer
            earliest = db.query(func.min(FeedbackItem.created_at)).filter(
                FeedbackItem.organization_id == ch.organization_id,
                FeedbackItem.customer_email == ch.customer_email,
            ).scalar()

            if earliest is None:
                # No feedback at all — seed a single point from now
                earliest = now - timedelta(weeks=1)

            # Clamp: don't go further back than 90 days
            cutoff = now - timedelta(days=90)
            start = max(earliest, cutoff)

            # Build weekly end-of-week timestamps from start to now
            # Each snapshot is the end of a 7-day window
            week_end = start + timedelta(weeks=1)
            weekly_dates = []
            while week_end <= now:
                weekly_dates.append(week_end)
                week_end += timedelta(weeks=1)

            # Always include a snapshot at "now" (current state)
            if not weekly_dates or weekly_dates[-1] < now - timedelta(hours=1):
                weekly_dates.append(now)

            for snap_date in weekly_dates:
                result = _compute_score_as_of(db, ch.organization_id, ch.customer_email, snap_date)
                batch.append(CustomerHealthHistory(
                    customer_health_id=ch.id,
                    organization_id=ch.organization_id,
                    health_score=result["health_score"],
                    churn_risk_component=result["churn_risk_component"],
                    sentiment_component=result["sentiment_component"],
                    resolution_component=result["resolution_component"],
                    frequency_component=result["frequency_component"],
                    risk_level=result["risk_level"],
                    recorded_at=snap_date,
                ))

            # Flush in batches to avoid huge transactions
            if len(batch) >= BATCH_SIZE:
                db.bulk_save_objects(batch)
                db.commit()
                total_inserted += len(batch)
                batch = []

            if idx % 10 == 0 or idx == len(customers):
                print(f"  Processed {idx}/{len(customers)} customers "
                      f"({total_inserted + len(batch)} records so far)")

        # Flush remaining
        if batch:
            db.bulk_save_objects(batch)
            db.commit()
            total_inserted += len(batch)

        print(f"\nDone. Inserted {total_inserted} weekly history records "
              f"across {len(customers)} customers.")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
