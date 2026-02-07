"""
Pytest configuration and fixtures for backend tests.
"""

import os
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.session import get_db
from src.models.base import Base
from src.models.user import User
from src.models.organization import Organization
from src.models.feedback import FeedbackItem
from src.models.integration import Integration, SlackAlertLog
from src.models.anomaly import SentimentAnomaly
from src.api.auth import hash_password, create_access_token


# Use in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_organization(db: Session) -> Organization:
    """Create a test organization with Pro plan (10 seat limit)."""
    org = Organization(
        name="Test Company",
        plan="pro"  # Pro plan has 10 seat limit for team tests
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def test_user(db: Session, test_organization: Organization) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="admin"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user_token(test_user: User) -> str:
    """Create a JWT token for test user."""
    return create_access_token({
        "user_id": test_user.id,
        "organization_id": test_user.organization_id,
        "role": test_user.role
    })


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    """Create authentication headers with JWT token."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def test_feedback(db: Session, test_organization: Organization) -> FeedbackItem:
    """Create test feedback item."""
    feedback = FeedbackItem(
        organization_id=test_organization.id,
        text="The product is amazing! I love it.",
        source="email",
        sentiment_label="positive",
        sentiment_score=0.95,
        extracted_issue=None,
        is_urgent=False
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@pytest.fixture
def test_feedback_batch(db: Session, test_organization: Organization) -> list[FeedbackItem]:
    """Create a batch of test feedback items with different sentiments."""
    feedbacks = [
        FeedbackItem(
            organization_id=test_organization.id,
            text="Great product! Very satisfied.",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.92,
            extracted_issue=None,
            is_urgent=False
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="The app crashes frequently. Very frustrating!",
            source="support_ticket",
            sentiment_label="negative",
            sentiment_score=-0.85,
            extracted_issue="App crashes",
            is_urgent=True
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="It's okay, nothing special.",
            source="survey",
            sentiment_label="neutral",
            sentiment_score=0.05,
            extracted_issue=None,
            is_urgent=False
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="Login is broken! Cannot access my account.",
            source="support_ticket",
            sentiment_label="negative",
            sentiment_score=-0.90,
            extracted_issue="Login broken",
            is_urgent=True
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="Would love to see dark mode feature.",
            source="email",
            sentiment_label="neutral",
            sentiment_score=0.10,
            extracted_issue="Dark mode feature request",
            is_urgent=False
        )
    ]

    for feedback in feedbacks:
        db.add(feedback)

    db.commit()

    for feedback in feedbacks:
        db.refresh(feedback)

    return feedbacks
