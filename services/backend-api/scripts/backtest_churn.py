"""
Backtest churn prediction accuracy against historical data.

Usage:
    python scripts/backtest_churn.py --days 30 --output results.csv --db-url postgresql://...

The script evaluates churn predictions by treating customers with no feedback
in the last `churn_days` days as "actually churned". It computes precision,
recall, F1, and accuracy for both churn_risk_score and health_score predictors.
"""
import argparse
import csv
import sys
import io
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Core logic (importable, testable without CLI)
# ---------------------------------------------------------------------------

def is_churned(customer_health_record, churn_days: int) -> bool:
    """
    Determine if a customer has churned based on last feedback date.

    A customer is considered 'actually churned' if their last_feedback_at
    is None or older than churn_days ago.
    """
    last_fb = customer_health_record.last_feedback_at
    if last_fb is None:
        return True
    cutoff = datetime.utcnow() - timedelta(days=churn_days)
    return last_fb < cutoff


def compute_metrics(tp: int, fp: int, fn: int, tn: int) -> Dict[str, float]:
    """
    Compute precision, recall, F1, and accuracy from confusion matrix counts.

    Returns a dict with keys: precision, recall, f1, accuracy.
    """
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def find_optimal_threshold(
    records: List[Dict],
    score_key: str,
    threshold_range: range = None,
) -> Tuple[int, float]:
    """
    Search for the threshold (20-80 step 5) that maximizes F1 score.

    Each record must have `score_key` (int) and `actually_churned` (bool).
    Returns (best_threshold, best_f1).
    """
    if threshold_range is None:
        threshold_range = range(20, 85, 5)

    best_threshold = 50
    best_f1 = -1.0

    for threshold in threshold_range:
        tp = fp = fn = tn = 0
        for r in records:
            score = r.get(score_key, 0) or 0
            predicted = score >= threshold
            actual = r["actually_churned"]
            if actual and predicted:
                tp += 1
            elif not actual and predicted:
                fp += 1
            elif actual and not predicted:
                fn += 1
            else:
                tn += 1

        metrics = compute_metrics(tp, fp, fn, tn)
        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            best_threshold = threshold

    return best_threshold, best_f1


def build_csv_rows(records: List[Dict], output_file) -> None:
    """
    Write backtest result rows to a CSV file-like object.

    CSV columns:
      customer_email, feedback_count, last_churn_risk_score, last_health_score,
      predicted_churn_by_risk, predicted_churn_by_health, actually_churned,
      days_since_last_feedback, correct_risk, correct_health
    """
    fieldnames = [
        "customer_email",
        "feedback_count",
        "last_churn_risk_score",
        "last_health_score",
        "predicted_churn_by_risk",
        "predicted_churn_by_health",
        "actually_churned",
        "days_since_last_feedback",
        "correct_risk",
        "correct_health",
    ]
    writer = csv.DictWriter(output_file, fieldnames=fieldnames)
    writer.writeheader()
    for row in records:
        writer.writerow({k: row[k] for k in fieldnames})


def check_data_sufficiency(customer_count: int) -> Optional[str]:
    """
    Return a warning string if the customer count is insufficient for backtest.
    Returns None when data is sufficient (>= 20 customers).
    """
    if customer_count < 20:
        return (
            f"Warning: Insufficient data for reliable backtest "
            f"(fewer than 20 customers evaluated, got {customer_count}). "
            f"Results may not be statistically significant."
        )
    return None


def run_backtest(db, churn_days: int = 30, organization_id: Optional[int] = None) -> Dict:
    """
    Run the full backtest against the database.

    Returns a summary dict with:
      - period_days
      - customers_evaluated
      - warning (if insufficient data)
      - churn_risk_metrics (precision/recall/f1/accuracy/optimal_threshold)
      - health_score_metrics (precision/recall/f1/accuracy)
      - rows (list of per-customer dicts for CSV export)
    """
    from src.models.customer_health import CustomerHealth

    CHURN_RISK_DEFAULT_THRESHOLD = 50
    HEALTH_SCORE_THRESHOLD = 50  # < 50 = predicted at risk

    query = db.query(CustomerHealth)
    if organization_id is not None:
        query = query.filter(CustomerHealth.organization_id == organization_id)
    records = query.all()

    now = datetime.utcnow()
    rows = []
    cr_tp = cr_fp = cr_fn = cr_tn = 0
    hs_tp = hs_fp = hs_fn = hs_tn = 0

    for r in records:
        actually_churned = is_churned(r, churn_days)
        cr_score = r.churn_risk_component or 0
        hs_score = r.health_score or 100
        cr_predicted = cr_score >= CHURN_RISK_DEFAULT_THRESHOLD
        hs_predicted = hs_score < HEALTH_SCORE_THRESHOLD

        days_since = None
        if r.last_feedback_at:
            days_since = (now - r.last_feedback_at).days

        if actually_churned and cr_predicted:
            cr_tp += 1
        elif not actually_churned and cr_predicted:
            cr_fp += 1
        elif actually_churned and not cr_predicted:
            cr_fn += 1
        else:
            cr_tn += 1

        if actually_churned and hs_predicted:
            hs_tp += 1
        elif not actually_churned and hs_predicted:
            hs_fp += 1
        elif actually_churned and not hs_predicted:
            hs_fn += 1
        else:
            hs_tn += 1

        rows.append({
            "customer_email": r.customer_email,
            "feedback_count": r.feedback_count or 0,
            "last_churn_risk_score": cr_score,
            "last_health_score": hs_score,
            "predicted_churn_by_risk": cr_predicted,
            "predicted_churn_by_health": hs_predicted,
            "actually_churned": actually_churned,
            "days_since_last_feedback": days_since,
            "correct_risk": (cr_predicted == actually_churned),
            "correct_health": (hs_predicted == actually_churned),
            "churn_risk_score": cr_score,
            "actually_churned": actually_churned,
        })

    cr_metrics = compute_metrics(cr_tp, cr_fp, cr_fn, cr_tn)
    hs_metrics = compute_metrics(hs_tp, hs_fp, hs_fn, hs_tn)

    # Find optimal threshold for churn risk score
    opt_threshold, opt_f1 = find_optimal_threshold(rows, score_key="churn_risk_score")
    cr_metrics["optimal_threshold"] = opt_threshold
    cr_metrics["optimal_f1"] = opt_f1

    return {
        "period_days": churn_days,
        "customers_evaluated": len(records),
        "warning": check_data_sufficiency(len(records)),
        "churn_risk_metrics": cr_metrics,
        "health_score_metrics": hs_metrics,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Backtest churn prediction accuracy")
    parser.add_argument("--days", type=int, default=30, help="Days to use for churn definition (default: 30)")
    parser.add_argument("--output", type=str, default=None, help="Path to save CSV results")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL (overrides env)")
    parser.add_argument("--org-id", type=int, default=None, help="Limit to specific organization ID")
    args = parser.parse_args()

    import os
    db_url = args.db_url or os.getenv("DATABASE_URL", "sqlite:///./rereflect.db")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        result = run_backtest(db, churn_days=args.days, organization_id=args.org_id)

        if result["warning"]:
            print(result["warning"], file=sys.stderr)

        print(f"\n=== Churn Prediction Backtest Results ===")
        print(f"Period: {result['period_days']} days")
        print(f"Customers evaluated: {result['customers_evaluated']}")

        print(f"\n--- Churn Risk Score Metrics (threshold=50) ---")
        cr = result["churn_risk_metrics"]
        print(f"  Precision: {cr['precision']:.4f}")
        print(f"  Recall:    {cr['recall']:.4f}")
        print(f"  F1:        {cr['f1']:.4f}")
        print(f"  Accuracy:  {cr['accuracy']:.4f}")
        print(f"  Optimal threshold: {cr['optimal_threshold']} (F1={cr['optimal_f1']:.4f})")

        print(f"\n--- Health Score Metrics (threshold=50) ---")
        hs = result["health_score_metrics"]
        print(f"  Precision: {hs['precision']:.4f}")
        print(f"  Recall:    {hs['recall']:.4f}")
        print(f"  F1:        {hs['f1']:.4f}")
        print(f"  Accuracy:  {hs['accuracy']:.4f}")

        if args.output:
            with open(args.output, "w", newline="") as f:
                build_csv_rows(result["rows"], f)
            print(f"\nCSV saved to: {args.output}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
