"""
Backfill customer health scores for all customers with customer_email set.
Run AFTER backfill_customer_email.py.
Run: cd services/backend-api && source venv/bin/activate && python scripts/backfill_health_scores.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func
from src.database.session import SessionLocal
from src.models.feedback import FeedbackItem
from src.services.health_score_service import update_customer_health


def main():
    db = SessionLocal()
    try:
        # Find all distinct org_id + customer_email pairs
        customers = db.query(
            FeedbackItem.organization_id,
            FeedbackItem.customer_email,
        ).filter(
            FeedbackItem.customer_email.isnot(None),
        ).group_by(
            FeedbackItem.organization_id,
            FeedbackItem.customer_email,
        ).all()

        print(f"Found {len(customers)} unique customers to compute health scores for")

        computed = 0
        errors = 0
        for org_id, email in customers:
            try:
                update_customer_health(org_id, email, db)
                computed += 1
            except Exception as e:
                print(f"  Error for {email} (org {org_id}): {e}")
                db.rollback()
                errors += 1

        db.commit()
        print(f"Computed {computed} health scores ({errors} errors)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
