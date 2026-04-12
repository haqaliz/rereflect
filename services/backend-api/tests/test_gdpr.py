"""
TDD tests for GDPR Compliance (Track A):
- Data export (ZIP)
- Deletion request
- Cancel deletion
- Deactivated user auth blocking
- Purge task
"""

import io
import json
import zipfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.api.main import app
from src.database.session import get_db
from src.models.conversation import Conversation
from src.models.conversation_message import ConversationMessage
from src.models.feedback import FeedbackItem
from src.models.feedback_note import FeedbackNote
from src.models.organization import Organization
from src.models.user import User
from src.models.user_alert_preference import UserAlertPreference


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db: Session, name: str = "GDPR Corp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(
    db: Session,
    org: Organization,
    email: str = "gdpr@example.com",
    role: str = "member",
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("secret123"),
        organization_id=org.id,
        role=role,
        joined_at=datetime(2025, 1, 15),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token(user: User) -> str:
    return create_access_token(
        {"user_id": user.id, "organization_id": user.organization_id, "role": user.role}
    )


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_token(user)}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.models.base import Base
from sqlalchemy import event as sa_event


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def _sqlite_date_trunc(part, value):
    from datetime import datetime as dt
    if value is None:
        return None
    if isinstance(value, str):
        value = dt.fromisoformat(value)
    if part == "day":
        return value.strftime("%Y-%m-%d 00:00:00")
    elif part == "week":
        from datetime import timedelta
        weekday = value.weekday()
        start = value - timedelta(days=weekday)
        return start.strftime("%Y-%m-%d 00:00:00")
    return value.strftime("%Y-%m-%d 00:00:00")


@sa_event.listens_for(engine, "connect")
def _register_sqlite_functions(dbapi_conn, connection_record):
    dbapi_conn.create_function("date_trunc", 2, _sqlite_date_trunc)


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _disable_emails():
    with patch("src.services.email_service._send_email", return_value=True):
        yield


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db: Session):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def org(db: Session) -> Organization:
    return _make_org(db)


@pytest.fixture()
def user(db: Session, org: Organization) -> User:
    return _make_user(db, org)


# ---------------------------------------------------------------------------
# Test 1: export returns a ZIP
# ---------------------------------------------------------------------------

def test_export_returns_zip(client: TestClient, db: Session, org: Organization, user: User):
    response = client.get("/api/v1/account/export", headers=_auth(user))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    # Verify it is actually a valid ZIP archive
    buf = io.BytesIO(response.content)
    assert zipfile.is_zipfile(buf)


# ---------------------------------------------------------------------------
# Test 2: ZIP contains profile.json with correct fields
# ---------------------------------------------------------------------------

def test_export_contains_profile_json(client: TestClient, db: Session, org: Organization, user: User):
    response = client.get("/api/v1/account/export", headers=_auth(user))
    assert response.status_code == 200

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf) as zf:
        assert "profile.json" in zf.namelist()
        profile = json.loads(zf.read("profile.json"))

    assert profile["email"] == user.email
    assert profile["role"] == user.role
    assert profile["org_name"] == org.name
    assert "joined_at" in profile


# ---------------------------------------------------------------------------
# Test 3: ZIP contains feedbacks files
# ---------------------------------------------------------------------------

def test_export_contains_feedbacks(client: TestClient, db: Session, org: Organization, user: User):
    # Create some feedback in the org
    for i in range(3):
        fb = FeedbackItem(
            organization_id=org.id,
            text=f"Test feedback {i}",
            source="manual",
            sentiment_label="positive",
        )
        db.add(fb)
    db.commit()

    response = client.get("/api/v1/account/export", headers=_auth(user))
    assert response.status_code == 200

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert "feedbacks.json" in names
        assert "feedbacks.csv" in names

        feedbacks = json.loads(zf.read("feedbacks.json"))
        assert len(feedbacks) == 3

        csv_content = zf.read("feedbacks.csv").decode("utf-8")
        # CSV should have header + 3 data rows
        lines = [l for l in csv_content.strip().splitlines() if l]
        assert len(lines) == 4  # 1 header + 3 rows


# ---------------------------------------------------------------------------
# Test 4: deletion request deactivates user
# ---------------------------------------------------------------------------

def test_deletion_request_deactivates_user(client: TestClient, db: Session, org: Organization, user: User):
    response = client.post("/api/v1/account/delete-request", headers=_auth(user))

    assert response.status_code == 200

    db.refresh(user)
    assert user.is_deactivated is True
    assert user.deletion_requested_at is not None


# ---------------------------------------------------------------------------
# Test 5: deactivated user cannot access the API
# ---------------------------------------------------------------------------

def test_deactivated_user_cannot_access_api(client: TestClient, db: Session, org: Organization, user: User):
    # Deactivate user directly
    user.is_deactivated = True
    db.commit()

    # Any protected endpoint should return 403
    response = client.get("/api/v1/account/export", headers=_auth(user))

    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 6: cancel deletion reactivates user
# ---------------------------------------------------------------------------

def test_cancel_deletion_reactivates_user(client: TestClient, db: Session, org: Organization, user: User):
    # First deactivate
    user.is_deactivated = True
    user.deletion_requested_at = datetime.utcnow() - timedelta(days=5)
    db.commit()

    # Cancel deletion — must work even when deactivated
    response = client.post("/api/v1/account/cancel-deletion", headers=_auth(user))

    assert response.status_code == 200

    db.refresh(user)
    assert user.is_deactivated is False
    assert user.deletion_requested_at is None


# ---------------------------------------------------------------------------
# Test 7: purge task deletes users after 30 days
# ---------------------------------------------------------------------------

def test_purge_deletes_after_30_days(db: Session, org: Organization):
    # Create user with deletion requested 31 days ago
    user_to_purge = _make_user(db, org, email="purge@example.com")
    user_to_purge.is_deactivated = True
    user_to_purge.deletion_requested_at = datetime.utcnow() - timedelta(days=31)
    db.commit()

    # Create a second user whose deletion was requested only 10 days ago (should NOT be purged)
    user_to_keep = _make_user(db, org, email="keep@example.com")
    user_to_keep.is_deactivated = True
    user_to_keep.deletion_requested_at = datetime.utcnow() - timedelta(days=10)
    db.commit()

    from src.background.gdpr_purge import check_deletion_requests

    check_deletion_requests(db)

    # purge@example.com should be gone
    gone = db.query(User).filter(User.email == "purge@example.com").first()
    assert gone is None

    # keep@example.com should still exist
    still_there = db.query(User).filter(User.email == "keep@example.com").first()
    assert still_there is not None
