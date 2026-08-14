"""Churn dataset builder (M5.3 churn-classifier-core).

Split into a pure transform (`rows_to_dataset`) and a lazy-SQL fetch seam
(`fetch_churn_rows`), mirroring corrections_classifier/dataset.py (DB collection
is a thin driver; the transform is pure and fully unit-testable with plain
dicts).

Label semantics mirror the calibrator (calibration_refit._collect_labels):
a label row is a `customer_churn_events` row with `source != 'auto_suggested'`
within the 180-day label window (LABEL_WINDOW_DAYS). The fetch LEFT JOINs the
CURRENT `customer_health_scores` / `customer_usage` values so each row carries
the feature fields; the nearest-at-label-date HISTORY snapshot values and the
feedback aggregates are attached by the CALLER (the worker trainer, aspect 4)
before rows_to_dataset runs — mirroring how the calibrator looks up
customer_health_history in Python rather than SQL. The SQL is written against
documented column names (the backend/worker model classes are not importable
in analysis-engine's env); only `fetch_churn_rows` needs sqlalchemy, and only
lazily.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .features import build_feature_vector


def rows_to_dataset(rows: list[dict]) -> dict:
    """Pure transform: raw row dicts -> {"features": [...], "labels": [...]}.

    Each row's feature vector comes from features.build_feature_vector (missing
    fields never raise — documented defaults). A row's label is
    `int(row["label"])`; rows from fetch_churn_rows are churn events, so a row
    WITHOUT a `label` key is a positive example (1). The caller attaches
    label=0 rows (non-churned customers in the active window) to build the
    binary dataset — same shape the calibrator's (scores, labels) pairs have.
    """
    features: list[list[float]] = []
    labels: list[int] = []
    for row in rows:
        features.append(build_feature_vector(row))
        labels.append(int(row.get("label", 1)))
    return {"features": features, "labels": labels}


def fetch_churn_rows(org_id: int, db, *, label_window_days: int = 180) -> list[dict]:
    """DB seam: qualifying churn-event rows for org_id (source != 'auto_suggested',
    churned_at within the label window), LEFT JOINed to the CURRENT
    customer_health_scores / customer_usage feature values.

    Column names are documented from the backend model definitions
    (models/churn_event.py, customer_health.py, customer_usage.py). The fetch is
    read-only; history snapshot values are attached by the caller.
    """
    from sqlalchemy import text

    cutoff = datetime.utcnow() - timedelta(days=label_window_days)

    query = text(
        """
        SELECT ce.customer_email                  AS customer_email,
               ce.churned_at                      AS churned_at,
               hs.health_score                    AS health_score,
               hs.churn_risk_component            AS churn_risk_component,
               hs.sentiment_component             AS sentiment_component,
               hs.resolution_component            AS resolution_component,
               hs.frequency_component             AS frequency_component,
               hs.usage_component                 AS usage_component,
               hs.crm_component                   AS crm_component,
               hs.risk_level                      AS risk_level,
               hs.segment                         AS segment,
               usg.active_days_7d                 AS active_days_7d,
               usg.active_days_14d                AS active_days_14d,
               usg.active_days_30d                AS active_days_30d,
               usg.login_count_30d                AS login_count_30d,
               usg.usage_score                    AS usage_score,
               usg.usage_trend_state              AS usage_trend_state,
               usg.usage_trend_pct                AS usage_trend_pct
        FROM customer_churn_events ce
        LEFT JOIN customer_health_scores hs
          ON hs.organization_id = ce.organization_id
         AND hs.customer_email = ce.customer_email
        LEFT JOIN customer_usage usg
          ON usg.organization_id = ce.organization_id
         AND usg.customer_email = ce.customer_email
        WHERE ce.organization_id = :org_id
          AND ce.source != 'auto_suggested'
          AND ce.churned_at >= :cutoff
        """
    )
    result = db.execute(query, {"org_id": org_id, "cutoff": cutoff})
    return [
        {
            "customer_email": row.customer_email,
            "churned_at": row.churned_at,
            "health_score": row.health_score,
            "churn_risk_component": row.churn_risk_component,
            "sentiment_component": row.sentiment_component,
            "resolution_component": row.resolution_component,
            "frequency_component": row.frequency_component,
            "usage_component": row.usage_component,
            "crm_component": row.crm_component,
            "risk_level": row.risk_level,
            "segment": row.segment,
            "active_days_7d": row.active_days_7d,
            "active_days_14d": row.active_days_14d,
            "active_days_30d": row.active_days_30d,
            "login_count_30d": row.login_count_30d,
            "usage_score": row.usage_score,
            "usage_trend_state": row.usage_trend_state,
            "usage_trend_pct": row.usage_trend_pct,
        }
        for row in result
    ]
