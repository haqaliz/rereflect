"""
Backfill customer_email on existing feedback items from source_metadata.
Run: cd services/backend-api && source venv/bin/activate && python scripts/backfill_customer_email.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database.session import SessionLocal
from src.models.feedback import FeedbackItem


def extract_email(source_metadata: dict) -> str | None:
    """Extract customer email from source_metadata."""
    if not source_metadata or not isinstance(source_metadata, dict):
        return None
    for key in ['author_email', 'email', 'sender_email', 'from_email', 'user_email']:
        val = source_metadata.get(key)
        if val and isinstance(val, str) and '@' in val:
            return val.lower().strip()
    return None


def main():
    db = SessionLocal()
    try:
        items = db.query(FeedbackItem).filter(
            FeedbackItem.customer_email == None,
            FeedbackItem.source_metadata != None,
        ).all()

        updated = 0
        for item in items:
            email = extract_email(item.source_metadata)
            if email:
                item.customer_email = email
                updated += 1

        db.commit()
        print(f"Backfilled {updated} of {len(items)} feedback items with customer_email")
    finally:
        db.close()


if __name__ == "__main__":
    main()
