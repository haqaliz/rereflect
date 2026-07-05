"""
TDD tests for the Asana create-task aspect (backend-create-task, Phase 2).

Covers: POST /tasks, GET /tasks (list linked).

Mocks AsanaClient at the route module (`src.api.routes.asana_integration.AsanaClient`)
per the repo's Jira/Linear/HubSpot integration test pattern — never hits the network.
"""
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.asana_integration import AsanaIntegration, FeedbackAsanaTask
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.organization import Organization
from src.models.user import User

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

WORKSPACE_GID = "1100000000001"
PROJECT_GID = "1200000000001"
API_TOKEN = "asana-super-secret-pat-xyz"

TASK_URL = "https://app.asana.com/0/1200000000001/1300000000001"


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="asana_issues_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_organization(db: Session) -> Organization:
    org = Organization(name="Other Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_org_feedback(db: Session, other_organization: Organization) -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=other_organization.id,
        text="Feedback from another org",
        source="email",
        sentiment_label="neutral",
        sentiment_score=0.0,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@pytest.fixture
def free_organization(db: Session) -> Organization:
    org = Organization(name="Free Asana Issues Co", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_owner_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free_asana_issues_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=free_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_owner_headers(free_owner_user: User) -> dict:
    token = create_access_token({
        "user_id": free_owner_user.id,
        "organization_id": free_owner_user.organization_id,
        "role": free_owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def free_feedback(db: Session, free_organization: Organization) -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=free_organization.id,
        text="Free plan feedback",
        source="email",
        sentiment_label="neutral",
        sentiment_score=0.0,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def _make_active_integration(db: Session, org_id: int) -> AsanaIntegration:
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        from src.utils.encryption import encrypt_api_key
        encrypted = encrypt_api_key(API_TOKEN)
    integration = AsanaIntegration(
        organization_id=org_id,
        api_token=encrypted,
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def asana_client_mock():
    """An AsanaClient mock instance with a default create_task."""
    mock_instance = MagicMock()
    mock_instance.create_task.return_value = {
        "gid": "1300000000001",
        "url": TASK_URL,
    }
    mock_instance.close = MagicMock()
    return mock_instance


def _create_task_payload(**overrides) -> dict:
    payload = {
        "workspace_gid": WORKSPACE_GID,
        "project_gid": PROJECT_GID,
        "name": "Customer reports login is broken",
        "notes": "Users cannot log in after the latest release.",
    }
    payload.update(overrides)
    return payload


# ──────────────────────────── POST /tasks ──────────────────────────────────────

class TestCreateTaskEndpoint:
    def test_happy_path_creates_task_row_and_timeline_event(
        self, client, db, test_organization, owner_user, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = asana_client_mock()
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["asana_task_gid"] == "1300000000001"
        assert body["asana_task_url"] == TASK_URL
        assert "asana_task_name" in body

        db.expire_all()
        rows = (
            db.query(FeedbackAsanaTask)
            .filter_by(feedback_id=test_feedback.id, organization_id=test_organization.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].asana_task_gid == "1300000000001"
        assert rows[0].asana_task_url == TASK_URL
        assert rows[0].created_by_user_id == owner_user.id

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter_by(feedback_id=test_feedback.id, event_type="asana_task_created")
            .all()
        )
        assert len(events) == 1

    def test_duplicate_without_force_returns_200_warning_no_second_call(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = asana_client_mock()
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                first_resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert first_resp.status_code == 200
        assert mock_client.create_task.call_count == 1

        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                second_resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert second_resp.status_code == 200
        assert second_resp.json()["warning"] == "duplicate"
        # No second Asana call was made.
        assert mock_client.create_task.call_count == 1

        db.expire_all()
        rows = (
            db.query(FeedbackAsanaTask)
            .filter_by(feedback_id=test_feedback.id, organization_id=test_organization.id)
            .all()
        )
        assert len(rows) == 1

    def test_force_creates_second_task(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = asana_client_mock()
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )

        mock_client.create_task.return_value = {
            "gid": "1300000000002",
            "url": "https://app.asana.com/0/1200000000001/1300000000002",
        }
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id, force=True),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["asana_task_gid"] == "1300000000002"
        assert mock_client.create_task.call_count == 2

        db.expire_all()
        rows = (
            db.query(FeedbackAsanaTask)
            .filter_by(feedback_id=test_feedback.id, organization_id=test_organization.id)
            .all()
        )
        assert len(rows) == 2

    def test_feedback_of_another_org_returns_404(
        self, client, db, test_organization, owner_headers, other_org_feedback
    ):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.asana_integration.AsanaClient",
            return_value=asana_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=other_org_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 404

    def test_empty_name_returns_422(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.asana_integration.AsanaClient",
            return_value=asana_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id, name=""),
                    headers=owner_headers,
                )
        assert resp.status_code == 422

    def test_name_over_limit_is_trimmed(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = asana_client_mock()
        long_name = "x" * 300
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(
                        feedback_id=test_feedback.id, name=long_name
                    ),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        call_kwargs = mock_client.create_task.call_args
        args, kwargs = call_kwargs
        payload = args[0] if args else kwargs
        assert len(payload["name"]) <= 255

    def test_stale_token_auth_error_returns_403_not_500(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        from src.services.asana_client import AsanaAuthError

        _make_active_integration(db, test_organization.id)
        mock_client = asana_client_mock()
        mock_client.create_task.side_effect = AsanaAuthError("401 invalid token")
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 403

        db.expire_all()
        row = (
            db.query(AsanaIntegration)
            .filter_by(organization_id=test_organization.id)
            .first()
        )
        assert row.last_error is not None
        assert row.last_sync_status == "error"

    def test_transient_error_returns_502(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        from src.services.asana_client import AsanaTransientError

        _make_active_integration(db, test_organization.id)
        mock_client = asana_client_mock()
        mock_client.create_task.side_effect = AsanaTransientError("503 upstream error")
        with patch(
            "src.api.routes.asana_integration.AsanaClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 502

    def test_unlocked_on_free_plan(
        self, client, db, free_organization, free_owner_headers, free_feedback
    ):
        _make_active_integration(db, free_organization.id)
        with patch(
            "src.api.routes.asana_integration.AsanaClient",
            return_value=asana_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=free_feedback.id),
                    headers=free_owner_headers,
                )
        assert resp.status_code == 200

    def test_no_active_integration_returns_404(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        resp = client.post(
            "/api/v1/integrations/asana/tasks",
            json=_create_task_payload(feedback_id=test_feedback.id),
            headers=owner_headers,
        )
        assert resp.status_code == 404


# ──────────────────────────── GET /tasks ───────────────────────────────────────

class TestGetLinkedTasksEndpoint:
    def test_lists_linked_tasks_for_feedback(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.asana_integration.AsanaClient",
            return_value=asana_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/asana/tasks",
                    json=_create_task_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )

        resp = client.get(
            "/api/v1/integrations/asana/tasks",
            params={"feedback_id": test_feedback.id},
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["asana_task_gid"] == "1300000000001"
        assert body[0]["asana_task_url"] == TASK_URL
