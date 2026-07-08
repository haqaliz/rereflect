"""
TDD tests for the segments Celery task — segment-engine Phase 4 (worker-service).

Acceptance criteria (from plan_20260708.md, Phase 4):
  - recompute_segments re-derives ``segment`` for every non-archived
    CustomerHealth row across all orgs, from the row's OWN stored fields
    (no health recompute).
  - Purely time-based flips (e.g. a customer going stale/dormant with no new
    activity) are picked up by a bare recompute — no new feedback/usage event
    required.
  - Archived rows are skipped entirely (not scanned, not touched).
  - 100% of non-archived rows end with a non-empty segment (coverage / PRD G2).
  - Return value reports accurate ``{"updated", "total"}`` counts.
  - A row whose recomputed segment equals its stored segment is not counted
    as updated.

Strategy: mirrors tests/test_usage_metrics.py — an isolated in-memory SQLite
engine (Base.metadata.create_all), a ``_fake_db_session`` context manager
patched over ``get_db_session``, and ``src.services.health_score_service``
injected via ``sys.modules`` so ``compute_sentiment_trend`` is a controllable
mock. The REAL duplicated ``src.services.segment_service`` (worker's own
copy of the classifier) is used unmocked, so these tests also exercise the
duplicated classifier end-to-end.
"""

import sys
import importlib
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# conftest already stubs src.config + src.database in sys.modules before this
# module is imported.
from src.models import Base, Organization, CustomerHealth, CustomerUsage


# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated from the conftest engine and from
# test_usage_metrics.py's own isolated engine)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@contextmanager
def _fake_db_session():
    """Thin context manager that yields a SQLite session (mirrors get_db_session)."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _fresh_db():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def db() -> Session:
    """Return a plain SQLite session for fixture setup."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session, name: str = "TestCorp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_health_row(
    db: Session,
    org_id: int,
    email: str,
    *,
    health_score: int = 50,
    risk_level: str = "healthy",
    churn_probability=None,
    feedback_count: int = 0,
    last_feedback_at=None,
    created_at=None,
    segment: str = None,
    is_archived: bool = False,
) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=health_score,
        risk_level=risk_level,
        churn_probability=churn_probability,
        feedback_count=feedback_count,
        last_feedback_at=last_feedback_at,
        created_at=created_at or (datetime.utcnow() - timedelta(days=200)),
        segment=segment,
        is_archived=is_archived,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_health_mock(direction_by_email: dict, default: str = "stable"):
    """
    Build a fake ``src.services.health_score_service`` module exposing
    ``compute_sentiment_trend(org_id, email, db) -> {"direction": ...}``.
    """
    health_mock = MagicMock()

    def _compute_sentiment_trend(org_id, email, db):
        direction = direction_by_email.get(email, default)
        return {"direction": direction, "change_percent": 0}

    health_mock.compute_sentiment_trend = MagicMock(side_effect=_compute_sentiment_trend)
    return health_mock


def _run_recompute(direction_by_email: dict = None, default: str = "stable"):
    """
    Run recompute_segments() with:
      - get_db_session patched to the test SQLite DB
      - src.services.health_score_service injected via sys.modules
    """
    health_mock = _make_health_mock(direction_by_email or {}, default=default)
    sys.modules["src.services.health_score_service"] = health_mock

    try:
        import src.tasks.segments as seg_task
        importlib.reload(seg_task)

        from unittest.mock import patch
        with patch.object(seg_task, "get_db_session", _fake_db_session):
            result = seg_task.recompute_segments()
        return result, health_mock
    finally:
        sys.modules.pop("src.services.health_score_service", None)


# ---------------------------------------------------------------------------
# Time-based flip: stale row with no usage row reclassified to dormant
# ---------------------------------------------------------------------------


class TestTimeBasedFlip:
    def test_stale_row_reclassified_to_dormant(self, db):
        """
        A "stale" CustomerHealth row (old last_feedback_at, no CustomerUsage
        row, otherwise healthy-looking) must flip to ``dormant`` on a bare
        recompute — proving time-based segments update without new activity.
        """
        org = _make_org(db)
        row = _make_health_row(
            db,
            org.id,
            "stale@example.com",
            health_score=80,
            risk_level="healthy",
            churn_probability=None,
            feedback_count=5,
            last_feedback_at=datetime.utcnow() - timedelta(days=100),
            created_at=datetime.utcnow() - timedelta(days=300),
            segment="happy_advocate",  # seeded stale/wrong value
            is_archived=False,
        )
        # No CustomerUsage row is created for this (org, email) — no-usage path.

        result, _ = _run_recompute({"stale@example.com": "stable"})

        db.expire(row)
        db.refresh(row)
        assert row.segment == "dormant"
        assert result["updated"] == 1
        assert result["total"] == 1


# ---------------------------------------------------------------------------
# Archived rows are skipped entirely
# ---------------------------------------------------------------------------


class TestArchivedRowsSkipped:
    def test_archived_row_not_touched(self, db):
        """An archived row must not be scanned or reclassified."""
        org = _make_org(db)
        row = _make_health_row(
            db,
            org.id,
            "archived@example.com",
            health_score=10,
            risk_level="critical",  # would classify as at_risk if processed
            churn_probability=0.9,
            feedback_count=0,
            last_feedback_at=None,
            created_at=datetime.utcnow() - timedelta(days=300),
            segment="power_user",  # deliberately "wrong" seeded value
            is_archived=True,
        )

        result, _ = _run_recompute()

        db.expire(row)
        db.refresh(row)
        assert row.segment == "power_user"  # unchanged
        assert result["total"] == 0
        assert result["updated"] == 0


# ---------------------------------------------------------------------------
# Coverage: 100% of non-archived rows end with a non-empty segment (PRD G2)
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_all_non_archived_rows_get_a_segment(self, db):
        org = _make_org(db)

        rows = [
            _make_health_row(
                db, org.id, "a@example.com",
                health_score=90, risk_level="healthy", churn_probability=None,
                feedback_count=1, last_feedback_at=datetime.utcnow() - timedelta(days=1),
                created_at=datetime.utcnow() - timedelta(days=1), segment=None,
            ),
            _make_health_row(
                db, org.id, "b@example.com",
                health_score=20, risk_level="at_risk", churn_probability=0.7,
                feedback_count=10, last_feedback_at=datetime.utcnow() - timedelta(days=2),
                created_at=datetime.utcnow() - timedelta(days=500), segment=None,
            ),
            _make_health_row(
                db, org.id, "c@example.com",
                health_score=50, risk_level="moderate", churn_probability=None,
                feedback_count=0, last_feedback_at=None,
                created_at=datetime.utcnow() - timedelta(days=500), segment=None,
            ),
        ]

        result, _ = _run_recompute()

        for row in rows:
            db.expire(row)
            db.refresh(row)
            assert row.segment is not None
            assert row.segment != ""

        assert result["total"] == 3


# ---------------------------------------------------------------------------
# Return counts are accurate
# ---------------------------------------------------------------------------


class TestReturnCounts:
    def test_updated_and_total_counts_are_accurate(self, db):
        org = _make_org(db)

        # This row's stored segment is wrong -> will be updated.
        _make_health_row(
            db, org.id, "wrong@example.com",
            health_score=10, risk_level="at_risk", churn_probability=0.9,
            feedback_count=1, last_feedback_at=datetime.utcnow() - timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(days=200), segment="new",
        )
        # This row's stored segment already matches -> not counted as updated.
        _make_health_row(
            db, org.id, "already_at_risk@example.com",
            health_score=10, risk_level="critical", churn_probability=0.9,
            feedback_count=1, last_feedback_at=datetime.utcnow() - timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(days=200), segment="at_risk",
        )
        # Archived row -> excluded from total entirely.
        _make_health_row(
            db, org.id, "archived2@example.com",
            health_score=10, risk_level="critical", churn_probability=0.9,
            feedback_count=1, last_feedback_at=datetime.utcnow() - timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(days=200), segment="whatever",
            is_archived=True,
        )

        result, _ = _run_recompute()

        assert result["total"] == 2
        assert result["updated"] == 1


# ---------------------------------------------------------------------------
# No-op: a row whose recompute yields the same segment is not counted
# ---------------------------------------------------------------------------


class TestNoOpNotCountedAsUpdated:
    def test_matching_segment_not_counted_as_updated(self, db):
        org = _make_org(db)
        # unsegmented: healthy-ish, no usage row, recent feedback, old enough
        # to not be "new", low health score so not happy_advocate.
        row = _make_health_row(
            db, org.id, "steady@example.com",
            health_score=50, risk_level="healthy", churn_probability=None,
            feedback_count=5, last_feedback_at=datetime.utcnow() - timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(days=200), segment="unsegmented",
        )

        result, _ = _run_recompute({"steady@example.com": "stable"})

        db.expire(row)
        db.refresh(row)
        assert row.segment == "unsegmented"
        assert result["updated"] == 0
        assert result["total"] == 1


# ---------------------------------------------------------------------------
# Registered as a Celery task
# ---------------------------------------------------------------------------


class TestCeleryRegistration:
    def test_recompute_segments_is_registered_celery_task(self):
        import src.tasks.segments as seg_task
        importlib.reload(seg_task)

        from src.celery_app import celery_app
        assert "src.tasks.segments.recompute_segments" in celery_app.tasks
