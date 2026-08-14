"""Tests for churn_classifier.dataset (M5.3 churn-classifier-core).

`rows_to_dataset` is pure (plain dicts in, no DB). `fetch_churn_rows` needs
sqlalchemy — guarded with `pytest.importorskip` so it skips gracefully where
sqlalchemy is unavailable (corrections_classifier/test_dataset.py convention).

The fetch mirrors the calibrator's label filter (customer_churn_events where
source != 'auto_suggested', within the label window) and joins the current
health/usage values so each row carries the feature fields; the nearest-
snapshot (at-label-date) history values and feedback aggregates are attached by
the CALLER (worker, aspect 4) — the fetch is read-only over the event table.
"""
from __future__ import annotations

import pytest

from src.analyzer.churn_classifier.dataset import fetch_churn_rows, rows_to_dataset
from src.analyzer.churn_classifier.features import FEATURE_NAMES, build_feature_vector


# ---------------------------------------------------------------------------
# rows_to_dataset — pure transform
# ---------------------------------------------------------------------------

def test_rows_to_dataset_builds_feature_vectors_and_positive_default_labels():
    row = {"churn_risk_component": 80, "usage_score": 30, "segment": "dormant"}
    result = rows_to_dataset([row])
    assert set(result.keys()) == {"features", "labels"}
    assert result["features"] == [build_feature_vector(row)]
    assert result["labels"] == [1]


def test_rows_to_dataset_respects_explicit_label():
    row = {"churn_risk_component": 40, "usage_score": 70, "label": 0}
    result = rows_to_dataset([row])
    assert result["labels"] == [0]


def test_rows_to_dataset_preserves_row_order():
    rows = [
        {"churn_risk_component": 80, "label": 1},
        {"churn_risk_component": 40, "label": 0},
        {"churn_risk_component": 90, "label": 1},
    ]
    result = rows_to_dataset(rows)
    assert result["labels"] == [1, 0, 1]
    assert [v[0] for v in result["features"]] == [80.0, 40.0, 90.0]


def test_rows_to_dataset_all_missing_fields_uses_defaults_no_raise():
    result = rows_to_dataset([{}, {"label": 0}])
    assert result["features"] == [build_feature_vector({}), build_feature_vector({})]
    assert result["labels"] == [1, 0]


def test_rows_to_dataset_empty_input():
    result = rows_to_dataset([])
    assert result == {"features": [], "labels": []}


def test_rows_to_dataset_feature_vectors_match_feature_names():
    result = rows_to_dataset([{"label": 1}, {"label": 0, "health_score": 70}])
    for vector in result["features"]:
        assert len(vector) == len(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# DB seam — fetch_churn_rows
# ---------------------------------------------------------------------------

sa = pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

_DDL = """
CREATE TABLE customer_churn_events (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    customer_email TEXT NOT NULL,
    churned_at TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT,
    recovered_at TEXT,
    marked_by_user_id INTEGER,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE customer_health_scores (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    customer_email TEXT NOT NULL,
    health_score INTEGER,
    churn_risk_component INTEGER,
    sentiment_component INTEGER,
    resolution_component INTEGER,
    frequency_component INTEGER,
    usage_component INTEGER,
    crm_component FLOAT,
    risk_level TEXT,
    segment TEXT,
    feedback_count INTEGER,
    last_feedback_at TEXT
);

CREATE TABLE customer_usage (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    customer_email TEXT NOT NULL,
    active_days_7d INTEGER,
    active_days_14d INTEGER,
    active_days_30d INTEGER,
    login_count_30d INTEGER,
    usage_score INTEGER,
    usage_trend_state TEXT,
    usage_trend_pct FLOAT
);
"""


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed(db, org_id: int = 1, other_org_id: int = 2):
    now = "2026-08-14T00:00:00"
    old = "2025-12-01T00:00:00"  # outside a 180-day window from now

    db.execute(
        text(
            "INSERT INTO customer_churn_events (id, organization_id, customer_email, churned_at,"
            " reason_code, reason_text, recovered_at, marked_by_user_id, source, created_at, updated_at)"
            " VALUES (:id, :org, :email, :churned_at, 'price', NULL, NULL, NULL, :source, :now, :now)"
        ),
        [
            dict(id=1, org=org_id, email="manual@example.com", churned_at=now, source="manual", now=now),
            dict(id=2, org=org_id, email="csv@example.com", churned_at=now, source="csv_import", now=now),
            dict(id=3, org=org_id, email="suggested@example.com", churned_at=now, source="auto_suggested", now=now),
            dict(id=4, org=org_id, email="old@example.com", churned_at=old, source="manual", now=now),
            dict(id=5, org=other_org_id, email="other@example.com", churned_at=now, source="manual", now=now),
        ],
    )

    db.execute(
        text(
            "INSERT INTO customer_health_scores (id, organization_id, customer_email, health_score,"
            " churn_risk_component, sentiment_component, resolution_component, frequency_component,"
            " usage_component, crm_component, risk_level, segment, feedback_count)"
            " VALUES (:id, :org, :email, :health_score, :churn_risk, 50, 50, 50, 50, 50.0,"
            " 'at_risk', :segment, 3)"
        ),
        [
            dict(id=1, org=org_id, email="manual@example.com", health_score=40, churn_risk=80, segment="dormant"),
            dict(id=2, org=org_id, email="csv@example.com", health_score=60, churn_risk=65, segment="at_risk"),
            dict(id=3, org=org_id, email="suggested@example.com", health_score=70, churn_risk=30, segment="power_user"),
            dict(id=4, org=org_id, email="old@example.com", health_score=50, churn_risk=55, segment="new"),
            dict(id=5, org=other_org_id, email="other@example.com", health_score=90, churn_risk=10, segment="happy_advocate"),
        ],
    )

    db.execute(
        text(
            "INSERT INTO customer_usage (id, organization_id, customer_email, active_days_7d,"
            " active_days_14d, active_days_30d, login_count_30d, usage_score, usage_trend_state, usage_trend_pct)"
            " VALUES (:id, :org, :email, :d7, :d14, :d30, :logins, :score, 'declining', :trend)"
        ),
        [
            dict(id=1, org=org_id, email="manual@example.com", d7=2, d14=5, d30=12, logins=8, score=35, trend=-40.0),
            dict(id=2, org=org_id, email="csv@example.com", d7=5, d14=9, d30=20, logins=15, score=55, trend=-15.0),
            dict(id=3, org=org_id, email="suggested@example.com", d7=10, d14=18, d30=27, logins=25, score=70, trend=5.0),
            dict(id=4, org=org_id, email="old@example.com", d7=4, d14=8, d30=18, logins=12, score=50, trend=0.0),
            dict(id=5, org=other_org_id, email="other@example.com", d7=12, d14=22, d30=29, logins=30, score=85, trend=10.0),
        ],
    )
    db.commit()


def test_fetch_filters_to_qualifying_events_only(db):
    _seed(db)
    rows = fetch_churn_rows(1, db)
    # manual + csv_import (in-window, org 1); auto_suggested, out-of-window and
    # other-org rows excluded.
    emails = [r["customer_email"] for r in rows]
    assert emails == ["manual@example.com", "csv@example.com"]


def test_fetch_carries_feature_fields_joined_from_health_and_usage(db):
    _seed(db)
    rows = fetch_churn_rows(1, db)
    by_email = {r["customer_email"]: r for r in rows}

    manual = by_email["manual@example.com"]
    assert manual["health_score"] == 40
    assert manual["churn_risk_component"] == 80
    assert manual["segment"] == "dormant"
    assert manual["active_days_7d"] == 2
    assert manual["active_days_30d"] == 12
    assert manual["usage_score"] == 35
    assert manual["usage_trend_state"] == "declining"
    assert manual["usage_trend_pct"] == -40.0
    assert manual["churned_at"] == "2026-08-14T00:00:00"

    csv_row = by_email["csv@example.com"]
    assert csv_row["churn_risk_component"] == 65
    assert csv_row["usage_score"] == 55


def test_fetch_scoped_to_org(db):
    _seed(db)
    rows = fetch_churn_rows(2, db)
    assert [r["customer_email"] for r in rows] == ["other@example.com"]


def test_fetch_label_window_filters_old_events(db):
    _seed(db)
    rows_90 = fetch_churn_rows(1, db, label_window_days=90)
    rows_400 = fetch_churn_rows(1, db, label_window_days=400)
    assert [r["customer_email"] for r in rows_90] == ["manual@example.com", "csv@example.com"]
    # 400-day window includes the old event (2025-12-01 is ~256 days before 2026-08-14).
    assert {r["customer_email"] for r in rows_400} == {
        "manual@example.com", "csv@example.com", "old@example.com",
    }


def test_fetch_returns_raw_rows_with_expected_keys(db):
    _seed(db)
    rows = fetch_churn_rows(1, db)
    for row in rows:
        assert set(row.keys()) >= {
            "customer_email",
            "churned_at",
            "health_score",
            "churn_risk_component",
            "segment",
            "usage_score",
            "active_days_30d",
        }


def test_fetch_left_join_with_missing_health_usage_rows_returns_nulls(db):
    db.execute(
        text(
            "INSERT INTO customer_churn_events (id, organization_id, customer_email, churned_at,"
            " reason_code, source, created_at, updated_at)"
            " VALUES (99, 1, 'no-health@example.com', '2026-08-14T00:00:00', 'other', 'manual',"
            " '2026-08-14T00:00:00', '2026-08-14T00:00:00')"
        )
    )
    db.commit()
    rows = fetch_churn_rows(1, db)
    row = next(r for r in rows if r["customer_email"] == "no-health@example.com")
    # LEFT JOIN: no health/usage row -> NULL feature fields (feature builder
    # turns them into documented defaults later).
    assert row["health_score"] is None
    assert row["usage_score"] is None


def test_fetch_with_empty_table_returns_empty_list(db):
    assert fetch_churn_rows(1, db) == []
