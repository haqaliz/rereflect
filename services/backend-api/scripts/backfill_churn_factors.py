"""
Backfill churn_risk_factors for existing feedback items that have a churn_risk_score
but no factor breakdown.

Also recomputes confidence_score on all CustomerHealth records.

Usage:
    python scripts/backfill_churn_factors.py [--batch-size 100] [--org-id ORG_ID] [--dry-run]
"""
import argparse
import sys
import os
from typing import Optional, List


# ---------------------------------------------------------------------------
# Core logic (importable, testable)
# ---------------------------------------------------------------------------

def get_items_to_backfill(db, org_id: Optional[int] = None) -> List:
    """
    Query feedback_items where:
    - churn_risk_factors IS NULL
    - churn_risk_score IS NOT NULL

    Returns a list of FeedbackItem ORM objects.
    """
    from src.models.feedback import FeedbackItem

    # SQLite stores Python None as JSON string 'null', so IS NULL doesn't match.
    # Fetch all scored items and filter in Python for missing factors.
    query = db.query(FeedbackItem).filter(
        FeedbackItem.churn_risk_score.isnot(None),
    )
    if org_id is not None:
        query = query.filter(FeedbackItem.organization_id == org_id)

    # Filter in Python: churn_risk_factors is None (or falsy JSON null)
    candidates = query.all()
    return [item for item in candidates if not item.churn_risk_factors]


def run_backfill(
    db,
    org_id: Optional[int] = None,
    batch_size: int = 100,
    dry_run: bool = False,
) -> int:
    """
    Backfill churn_risk_factors for feedback items missing them.

    Also recomputes confidence_score on all CustomerHealth records for the org.

    Returns the count of items updated (or that would be updated in dry-run mode).
    """
    # Import inside function to avoid circular imports at module level
    import sys
    import os

    # Ensure worker service src is on path for _compute_heuristic_churn_risk
    worker_src = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../worker-service/src")
    )
    if worker_src not in sys.path:
        sys.path.insert(0, worker_src)

    try:
        from tasks.analysis import _compute_heuristic_churn_risk
    except ImportError:
        # Fallback: build a minimal factor dict from existing score
        def _compute_heuristic_churn_risk(feedback, db=None):
            score = feedback.churn_risk_score or 0
            factors = {
                "sentiment": {"score": 0, "max": 15, "label": "Backfilled"},
                "churn_keywords": {"score": 0, "max": 15, "label": "Backfilled"},
                "frustration_keywords": {"score": 0, "max": 10, "label": "Backfilled"},
                "urgency": {"score": 0, "max": 10, "label": "Backfilled"},
                "sentiment_trend": {"score": 0, "max": 15, "label": "Backfilled"},
                "feedback_frequency": {"score": 0, "max": 10, "label": "Backfilled"},
                "resolution_time": {"score": 0, "max": 10, "label": "Backfilled"},
                "pain_severity": {"score": 0, "max": 10, "label": "Backfilled"},
                "feature_density": {"score": 0, "max": 5, "label": "Backfilled"},
            }
            return score, factors

    items = get_items_to_backfill(db, org_id=org_id)
    total = len(items)

    if dry_run:
        print(f"[DRY RUN] Would update {total} feedback items.", file=sys.stderr)
        return total

    updated = 0
    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        for item in batch:
            try:
                _score, factors = _compute_heuristic_churn_risk(item, db=db)
                item.churn_risk_factors = factors
                updated += 1
            except Exception as e:
                print(f"Error processing feedback {item.id}: {e}", file=sys.stderr)

        db.commit()
        print(f"Processed {min(i + batch_size, total)}/{total} items...", file=sys.stderr)

    # Recompute confidence_score for all CustomerHealth records
    _recompute_confidence_scores(db, org_id=org_id)

    return updated


def _recompute_confidence_scores(db, org_id: Optional[int] = None) -> int:
    """
    Recompute confidence_score on all CustomerHealth records using current feedback data.

    Returns the count of records updated.
    """
    from src.models.customer_health import CustomerHealth
    from src.services.health_score_service import update_customer_health

    query = db.query(CustomerHealth)
    if org_id is not None:
        query = query.filter(CustomerHealth.organization_id == org_id)

    records = query.all()
    updated = 0

    for record in records:
        try:
            update_customer_health(record.organization_id, record.customer_email, db)
            updated += 1
        except Exception as e:
            print(f"Error updating health for {record.customer_email}: {e}", file=sys.stderr)

    return updated


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Backfill churn_risk_factors for existing feedback items."
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for commits (default: 100)")
    parser.add_argument("--org-id", type=int, default=None, help="Limit backfill to specific organization ID")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be updated without writing")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL (overrides env)")
    args = parser.parse_args()

    db_url = args.db_url or os.getenv("DATABASE_URL", "sqlite:///./rereflect.db")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        count = run_backfill(
            db,
            org_id=args.org_id,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        mode = "Would update" if args.dry_run else "Updated"
        print(f"\n{mode} {count} feedback items with churn_risk_factors.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
