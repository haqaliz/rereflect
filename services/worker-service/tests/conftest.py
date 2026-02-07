"""
Pytest configuration and fixtures for worker service tests.
"""

import sys
from contextlib import contextmanager
from unittest.mock import MagicMock

# Mock src.config and src.database before any task module imports them.
# This avoids pydantic Settings() validation against the real .env file.
_mock_config = MagicMock()
_mock_config.settings = MagicMock()
sys.modules.setdefault("src.config", _mock_config)

_mock_database = MagicMock()

@contextmanager
def _fake_get_db_session():
    yield MagicMock()

_mock_database.get_db_session = _fake_get_db_session
sys.modules.setdefault("src.database", _mock_database)

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, User, Organization, FeedbackItem, CustomCategory


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_org(db):
    """Create a test organization."""
    org = Organization(name="Test Corp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def ai_enabled_org(db):
    """Create an organization with AI analysis enabled."""
    org = Organization(name="AI Corp", plan="business", ai_analysis_enabled=True)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def ai_disabled_org(db):
    """Create an organization with AI analysis disabled."""
    org = Organization(name="No AI Corp", plan="pro", ai_analysis_enabled=False)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def custom_categories(db, ai_enabled_org):
    """Create custom categories for AI-enabled org."""
    cats = [
        CustomCategory(
            organization_id=ai_enabled_org.id,
            name="onboarding_issues",
            description="Issues during user onboarding",
            category_type="pain_point",
        ),
        CustomCategory(
            organization_id=ai_enabled_org.id,
            name="api_requests",
            description="Requests for API features",
            category_type="feature_request",
        ),
    ]
    for c in cats:
        db.add(c)
    db.commit()
    return cats


@pytest.fixture
def unanalyzed_feedback(db, ai_enabled_org):
    """Create unanalyzed feedback for AI-enabled org."""
    feedback = FeedbackItem(
        organization_id=ai_enabled_org.id,
        text="The app crashes every time I try to export data. This is really frustrating!",
        source="support",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@pytest.fixture
def test_user(db, test_org):
    """Create a test user with digest enabled."""
    user = User(
        email="user@test.com",
        organization_id=test_org.id,
        role="owner",
        weekly_digest_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def opted_out_user(db, test_org):
    """Create a user who opted out of weekly digest."""
    user = User(
        email="optout@test.com",
        organization_id=test_org.id,
        role="member",
        weekly_digest_enabled=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def recent_feedback(db, test_org):
    """Create feedback from the past 7 days with mixed sentiments."""
    now = datetime.utcnow()
    feedbacks = [
        FeedbackItem(
            organization_id=test_org.id,
            text="Great product!",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            created_at=now - timedelta(days=1),
        ),
        FeedbackItem(
            organization_id=test_org.id,
            text="App crashes on login",
            source="support",
            sentiment_label="negative",
            sentiment_score=-0.8,
            pain_point_category="bugs",
            pain_point_severity="critical",
            is_urgent=True,
            created_at=now - timedelta(days=2),
        ),
        FeedbackItem(
            organization_id=test_org.id,
            text="Would like dark mode",
            source="email",
            sentiment_label="neutral",
            sentiment_score=0.1,
            feature_request_category="ui",
            feature_request_priority="medium",
            is_urgent=False,
            created_at=now - timedelta(days=3),
        ),
    ]
    for f in feedbacks:
        db.add(f)
    db.commit()
    return feedbacks


@pytest.fixture
def old_feedback(db, test_org):
    """Create feedback older than 7 days (should not be included in digest)."""
    old = FeedbackItem(
        organization_id=test_org.id,
        text="Old feedback",
        source="email",
        sentiment_label="positive",
        sentiment_score=0.9,
        is_urgent=False,
        created_at=datetime.utcnow() - timedelta(days=14),
    )
    db.add(old)
    db.commit()
    return old
