"""
TDD tests for the Jira create-issue aspect (backend-create-issue, Phase 4).

Covers: text_to_adf helper, GET /projects, GET /issuetypes, POST /issues,
GET /issues (list linked).

Mocks JiraClient at the route module (`src.api.routes.jira_integration.JiraClient`)
per the repo's Linear/HubSpot/Jira-connection test pattern — never hits the network.
"""
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.jira_integration import FeedbackJiraIssue, JiraIntegration
from src.models.organization import Organization
from src.models.user import User

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"
API_TOKEN = "atlassian-super-secret-token-xyz"


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="jira_issues_owner@test.com",
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
    org = Organization(name="Free Jira Issues Co", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_owner_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free_jira_issues_owner@test.com",
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


def _make_active_integration(db: Session, org_id: int) -> JiraIntegration:
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        from src.utils.encryption import encrypt_api_key
        encrypted = encrypt_api_key(API_TOKEN)
    integration = JiraIntegration(
        organization_id=org_id,
        site_url=SITE_URL,
        email=EMAIL,
        api_token=encrypted,
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def jira_client_mock():
    """A JiraClient mock instance with default get_projects/get_issue_types/create_issue."""
    mock_instance = MagicMock()
    mock_instance.get_projects.return_value = [
        {"id": "10000", "key": "ENG", "name": "Engineering"},
    ]
    mock_instance.get_issue_types.return_value = [
        {"id": "10001", "name": "Bug"},
        {"id": "10002", "name": "Task"},
    ]
    mock_instance.create_issue.return_value = {
        "id": "20001",
        "key": "ENG-142",
        "url": f"{SITE_URL}/browse/ENG-142",
    }
    mock_instance.close = MagicMock()
    return mock_instance


def _create_issue_payload(**overrides) -> dict:
    payload = {
        "project_id": "10000",
        "issue_type_id": "10001",
        "summary": "Customer reports login is broken",
        "description": "Users cannot log in after the latest release.",
    }
    payload.update(overrides)
    return payload


# ──────────────────────────── text_to_adf unit tests ──────────────────────────

class TestTextToAdf:
    def test_wraps_plain_text_into_valid_adf(self):
        from src.services.jira_client import text_to_adf

        doc = text_to_adf("Hello world")
        assert doc == {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }

    def test_empty_text_returns_valid_empty_doc(self):
        from src.services.jira_client import text_to_adf

        doc = text_to_adf("")
        assert doc["type"] == "doc"
        assert doc["version"] == 1
        # No empty text node inside the paragraph's content.
        assert doc["content"] == [{"type": "paragraph", "content": []}]

    def test_none_text_returns_valid_empty_doc(self):
        from src.services.jira_client import text_to_adf

        doc = text_to_adf(None)
        assert doc["content"] == [{"type": "paragraph", "content": []}]


# ──────────────────────────── GET /projects ────────────────────────────────────

class TestProjectsEndpoint:
    def test_get_projects_proxies_client(self, client, db, test_organization, owner_headers):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.get(
                    "/api/v1/integrations/jira/projects", headers=owner_headers
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body == [{"id": "10000", "key": "ENG", "name": "Engineering"}]

    def test_get_projects_400_when_not_connected(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/jira/projects", headers=owner_headers
        )
        assert resp.status_code == 400


# ──────────────────────────── GET /issuetypes ──────────────────────────────────

class TestIssueTypesEndpoint:
    def test_get_issuetypes_proxies_client(self, client, db, test_organization, owner_headers):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.get(
                    "/api/v1/integrations/jira/issuetypes",
                    params={"project_id": "10000"},
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body == [
            {"id": "10001", "name": "Bug"},
            {"id": "10002", "name": "Task"},
        ]

    def test_get_issuetypes_400_when_not_connected(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/jira/issuetypes",
            params={"project_id": "10000"},
            headers=owner_headers,
        )
        assert resp.status_code == 400


# ──────────────────────────── POST /issues ─────────────────────────────────────

class TestCreateIssueEndpoint:
    def test_happy_path_creates_issue_row_and_timeline_event(
        self, client, db, test_organization, owner_user, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = jira_client_mock()
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["jira_issue_key"] == "ENG-142"
        assert body["jira_issue_url"] == f"{SITE_URL}/browse/ENG-142"
        assert body["jira_issue_id"] == "20001"
        assert "jira_issue_title" in body

        db.expire_all()
        rows = (
            db.query(FeedbackJiraIssue)
            .filter_by(feedback_id=test_feedback.id, organization_id=test_organization.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].jira_issue_key == "ENG-142"
        assert rows[0].created_by_user_id == owner_user.id

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter_by(feedback_id=test_feedback.id, event_type="jira_issue_created")
            .all()
        )
        assert len(events) == 1

    def test_duplicate_without_force_returns_200_warning_no_second_row(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = jira_client_mock()
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                first_resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert first_resp.status_code == 200

        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                second_resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert second_resp.status_code == 200
        assert second_resp.json()["warning"] == "duplicate"

        db.expire_all()
        rows = (
            db.query(FeedbackJiraIssue)
            .filter_by(feedback_id=test_feedback.id, organization_id=test_organization.id)
            .all()
        )
        assert len(rows) == 1

    def test_force_creates_second_issue(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = jira_client_mock()
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )

        mock_client.create_issue.return_value = {
            "id": "20002",
            "key": "ENG-143",
            "url": f"{SITE_URL}/browse/ENG-143",
        }
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id, force=True),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["jira_issue_key"] == "ENG-143"

        db.expire_all()
        rows = (
            db.query(FeedbackJiraIssue)
            .filter_by(feedback_id=test_feedback.id, organization_id=test_organization.id)
            .all()
        )
        assert len(rows) == 2

    def test_feedback_of_another_org_returns_404(
        self, client, db, test_organization, owner_headers, other_org_feedback
    ):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=other_org_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 404

    def test_empty_summary_returns_422(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id, summary=""),
                    headers=owner_headers,
                )
        assert resp.status_code == 422

    def test_summary_over_255_chars_is_trimmed(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        mock_client = jira_client_mock()
        long_summary = "x" * 300
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(
                        feedback_id=test_feedback.id, summary=long_summary
                    ),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        call_kwargs = mock_client.create_issue.call_args
        # find the "summary" passed to the client — support both positional dict and kwargs
        args, kwargs = call_kwargs
        payload = args[0] if args else kwargs
        assert len(payload["summary"]) == 255

    def test_stale_token_auth_error_returns_403_or_422_not_500(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        from src.services.jira_client import JiraAuthError

        integration = _make_active_integration(db, test_organization.id)
        mock_client = jira_client_mock()
        mock_client.create_issue.side_effect = JiraAuthError("401 invalid token")
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code in (403, 422)

        db.expire_all()
        row = (
            db.query(JiraIntegration)
            .filter_by(organization_id=test_organization.id)
            .first()
        )
        assert row.last_error is not None

    def test_transient_error_returns_502(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        from src.services.jira_client import JiraTransientError

        _make_active_integration(db, test_organization.id)
        mock_client = jira_client_mock()
        mock_client.create_issue.side_effect = JiraTransientError("503 upstream error")
        with patch(
            "src.api.routes.jira_integration.JiraClient", return_value=mock_client
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )
        assert resp.status_code == 502

    def test_unlocked_on_free_plan(
        self, client, db, free_organization, free_owner_headers, free_feedback
    ):
        _make_active_integration(db, free_organization.id)
        with patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=free_feedback.id),
                    headers=free_owner_headers,
                )
        assert resp.status_code == 200


# ──────────────────────────── GET /issues ──────────────────────────────────────

class TestGetLinkedIssuesEndpoint:
    def test_lists_linked_issues_for_feedback(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        _make_active_integration(db, test_organization.id)
        with patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_mock(),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/jira/issues",
                    json=_create_issue_payload(feedback_id=test_feedback.id),
                    headers=owner_headers,
                )

        resp = client.get(
            "/api/v1/integrations/jira/issues",
            params={"feedback_id": test_feedback.id},
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["jira_issue_key"] == "ENG-142"
