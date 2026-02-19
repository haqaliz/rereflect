"""
Backfill initial health score history for existing customers who have no history records.
This seeds the first data point so the Health Score History chart has something to show.

Run: cd services/backend-api && source venv/bin/activate && python scripts/backfill_health_history.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database.session import SessionLocal
from src.models.customer_health import CustomerHealth
from src.models.customer_health_history import CustomerHealthHistory


def main():
    db = SessionLocal()
    try:
        # Find all CustomerHealth records that have NO history entries
        customers_with_history = (
            db.query(CustomerHealthHistory.customer_health_id)
            .distinct()
            .subquery()
        )

        customers_without_history = (
            db.query(CustomerHealth)
            .filter(CustomerHealth.id.notin_(
                db.query(customers_with_history.c.customer_health_id)
            ))
            .all()
        )

        print(f"Found {len(customers_without_history)} customers with no history records")

        created = 0
        for ch in customers_without_history:
            history = CustomerHealthHistory(
                customer_health_id=ch.id,
                organization_id=ch.organization_id,
                health_score=ch.health_score,
                churn_risk_component=ch.churn_risk_component,
                sentiment_component=ch.sentiment_component,
                resolution_component=ch.resolution_component,
                frequency_component=ch.frequency_component,
                risk_level=ch.risk_level,
                recorded_at=ch.updated_at or ch.created_at,
            )
            db.add(history)
            created += 1

        db.commit()
        print(f"Created {created} initial history records")
    finally:
        db.close()


if __name__ == "__main__":
    main()
