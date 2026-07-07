"""
Celery task for nightly customer-segment recompute (segment-engine aspect,
Phase 4).

``recompute_segments`` re-derives ``segment`` for every non-archived
``CustomerHealth`` row across all orgs, from the row's OWN already-computed
fields (health_score, risk_level, churn_probability, feedback_count,
last_feedback_at, created_at), the customer's ``CustomerUsage`` rollup (if
any), and a freshly-computed sentiment-trend direction. This task never
recomputes health itself — it only re-runs the classifier so purely
time-based segments (``dormant``, ``silent_churner``, ``new``) flip even when
no new feedback/usage event arrives (critique gap #1 — see plan_20260708.md
Phase 4).

Beat registration: see celery_app.py (``recompute-segments-daily``, 04:15
UTC, after ``recompute-usage-scores-daily`` at 04:00 UTC).
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Dict

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)


@shared_task(name="src.tasks.segments.recompute_segments")
def recompute_segments() -> Dict[str, int]:
    """
    Re-derive ``segment`` for every non-archived CustomerHealth row.

    Archived rows (``is_archived == True``) are skipped entirely — they are
    excluded from the query, so they are never scanned, never counted in
    ``total``, and never reclassified.

    For each scanned row:
      - Build ``UsageSignals`` from the matching ``CustomerUsage`` row for
        (organization_id, customer_email), or ``None`` if no such row exists.
      - Compute the sentiment-trend ``direction`` via
        ``compute_sentiment_trend`` (lazy cross-service import — the module
        lives in backend-api's ``health_score_service`` but is imported here
        exactly like ``usage_metrics.py`` imports ``update_customer_health``).
      - Call the (worker's own, duplicated) ``classify_segment`` with the
        row's stored fields.
      - If the recomputed slug differs from ``row.segment``, update it and
        count the row as updated.

    A per-row classification failure is logged and the row is skipped (not
    counted as scanned successfully, not committed) so that one bad row can
    never abort the whole run.

    Beat schedule: daily, 04:15 UTC — see celery_app.py
    ``recompute-segments-daily``.

    Returns:
        dict with ``updated`` (rows whose segment changed) and ``total``
        (non-archived rows scanned).
    """
    from src.models import CustomerHealth, CustomerUsage
    from src.services.segment_service import classify_segment, UsageSignals

    updated = 0
    total = 0
    segment_counts: Counter = Counter()

    with get_db_session() as db:
        rows = (
            db.query(CustomerHealth)
            .filter(CustomerHealth.is_archived == False)  # noqa: E712
            .all()
        )
        now = datetime.utcnow()

        for row in rows:
            total += 1
            try:
                usage_row = (
                    db.query(CustomerUsage)
                    .filter_by(
                        organization_id=row.organization_id,
                        customer_email=row.customer_email,
                    )
                    .first()
                )
                usage = (
                    UsageSignals(
                        last_active_at=usage_row.last_active_at,
                        active_days_30d=usage_row.active_days_30d,
                        distinct_feature_count=usage_row.distinct_feature_count,
                        usage_score=usage_row.usage_score,
                        first_seen_at=usage_row.first_seen_at,
                    )
                    if usage_row is not None
                    else None
                )

                # Lazy cross-service import: this module lives only in
                # backend-api, but resolves at task runtime the same way
                # usage_metrics.py imports update_customer_health.
                from src.services.health_score_service import compute_sentiment_trend

                sentiment = compute_sentiment_trend(row.organization_id, row.customer_email, db)
                direction = sentiment.get("direction") if sentiment else None

                new_segment = classify_segment(
                    health_score=row.health_score,
                    risk_level=row.risk_level,
                    churn_probability=row.churn_probability,
                    feedback_count=row.feedback_count,
                    last_feedback_at=row.last_feedback_at,
                    created_at=row.created_at,
                    usage=usage,
                    sentiment_direction=direction,
                    now=now,
                )
            except Exception:
                logger.exception(
                    "recompute_segments: failed to classify row id=%s org=%s "
                    "email=%s — skipping",
                    getattr(row, "id", None), row.organization_id, row.customer_email,
                )
                continue

            segment_counts[new_segment] += 1

            if new_segment != row.segment:
                row.segment = new_segment
                updated += 1

        if updated:
            db.commit()

    logger.info(
        "recompute_segments: scanned=%s updated=%s by_segment=%s",
        total, updated, dict(segment_counts),
    )
    return {"updated": updated, "total": total}
