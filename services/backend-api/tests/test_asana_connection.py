"""
TDD tests for the Asana connection routes (backend-connection aspect, Phase 3).

Covers: POST /connect, GET /status, DELETE /disconnect, POST /test,
GET /workspaces, GET /projects.

Mocks AsanaClient at the route module
(`src.api.routes.asana_integration.AsanaClient`) per the repo's Jira/Zendesk
test pattern — never hits the network.

Asana is Bearer-PAT-only against a fixed host, so unlike Jira there is no
site_url/email in the connect payload and no SSRF DNS gate to mock.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.asana_integration import AsanaIntegration, FeedbackAsanaTask
from src.api.auth import hash_password, create_access_token


# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

API_TOKEN = "asana-super-secret-pat-xyz"


def asana_client_ok(gid="123456789", name="Jane Operator"):
    """An AsanaClient mock instance whose validate() succeeds."""
    mock_instance = MagicMock()
    mock_instance.validate.return_value = {"gid": gid, "name": name}
    mock_instance.close = MagicMock()
    return mock_instance


def asana_client_auth_fail():
    """An AsanaClient mock instance whose validate() raises AsanaAuthError."""
    from src.services.asana_client import AsanaAuthError

    mock_instance = MagicMock()
    mock_instance.validate.side_effect = AsanaAuthError("401 invalid token")
    mock_instance.close = MagicMock()
    return mock_instance


def asana_client_transient_fail():
    """An AsanaClient mock instance whose validate() raises AsanaTransientError."""
    from src.services.asana_client import AsanaTransientError

    mock_instance = MagicMock()
    mock_instance.validate.side_effect = AsanaTransientError("503 upstream error")
    mock_instance.close = MagicMock()
    return mock_instance


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="asana_owner@test.com",
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
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="asana_member@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def free_organization(db: Session) -> Organization:
    """An organization on the Free plan — the asana_integration feature must be unlocked here."""
    org = Organization(name="Free Asana Co", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_owner_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free_asana_owner@test.com",
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


def _connect_payload(**overrides) -> dict:
    payload = {"api_token": API_TOKEN}
    payload.update(overrides)
    return payload


# ──────────────────────────── POST /connect ───────────────────────────────────

class TestConnectEndpoint:
    def test_connect_valid_token_returns_200_with_expected_fields(self, client, owner_headers):
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["token_hint"] is not None
        assert body["account_gid"] == "123456789"
        assert body["display_name"] == "Jane Operator"

    def test_connect_response_never_contains_api_token(self, client, owner_headers):
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        body = resp.json()
        assert "api_token" not in body
        assert API_TOKEN not in str(body)

    def test_connect_stores_encrypted_token_not_plaintext(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(organization_id=test_organization.id).first()
        assert row is not None
        assert row.api_token != API_TOKEN, "Token must be encrypted at rest"
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(row.api_token) == API_TOKEN

    def test_connect_invalid_token_returns_422_and_persists_no_row(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_auth_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 422
        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(organization_id=test_organization.id).first()
        assert row is None

    def test_connect_transient_error_returns_502(self, client, owner_headers):
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_transient_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 502

    def test_connect_missing_encryption_key_returns_422_not_500(self, client, owner_headers):
        with (
            patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()),
            patch(
                "src.api.routes.asana_integration.encrypt_api_key",
                side_effect=ValueError("LLM_ENCRYPTION_KEY environment variable is not set"),
            ),
        ):
            resp = client.post(
                "/api/v1/integrations/asana/connect",
                json=_connect_payload(),
                headers=owner_headers,
            )
        assert resp.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in resp.json()["detail"]

    def test_connect_missing_api_token_returns_422(self, client, owner_headers):
        resp = client.post(
            "/api/v1/integrations/asana/connect",
            json={},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_connect_reconnect_reuses_row_and_rotates_token(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                first_resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert first_resp.status_code == 200
        db.expire_all()
        first_row = db.query(AsanaIntegration).filter_by(organization_id=test_organization.id).first()
        first_id = first_row.id
        first_token_hint = first_row.token_hint

        new_token = "asana-rotated-token-9999"
        with patch(
            "src.api.routes.asana_integration.AsanaClient",
            return_value=asana_client_ok(gid="new-gid", name="New Name"),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                second_resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(api_token=new_token),
                    headers=owner_headers,
                )
        assert second_resp.status_code == 200

        db.expire_all()
        rows = db.query(AsanaIntegration).filter_by(organization_id=test_organization.id).all()
        assert len(rows) == 1, "Unique constraint must hold — reconnect must not create a 2nd row"
        row = rows[0]
        assert row.id == first_id
        assert row.is_active is True
        assert row.token_hint != first_token_hint
        assert row.token_hint == "...9999"
        from src.utils.encryption import decrypt_api_key
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            assert decrypt_api_key(row.api_token) == new_token


# ──────────────────────────── GET /status ──────────────────────────────────────

class TestStatusEndpoint:
    def test_status_disconnected_when_no_integration(self, client, owner_headers):
        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_status_connected_returns_full_status(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token="encrypted-blob",
            token_hint="...wxyz",
            account_gid="acc-1",
            display_name="Display Name",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["token_hint"] == "...wxyz"
        assert body["account_gid"] == "acc-1"
        assert body["display_name"] == "Display Name"
        assert "api_token" not in body
        assert "encrypted-blob" not in str(body)

    def test_status_requires_auth(self, client):
        resp = client.get("/api/v1/integrations/asana/status")
        assert resp.status_code == 403


# ──────────────────────────── DELETE /disconnect ───────────────────────────────

class TestDisconnectEndpoint:
    def test_disconnect_sets_inactive(self, client, db, test_organization, owner_headers):
        from datetime import datetime
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.delete("/api/v1/integrations/asana/disconnect", headers=owner_headers)
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(organization_id=test_organization.id).first()
        assert row.is_active is False

    def test_disconnect_preserves_feedback_asana_task_rows(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        from datetime import datetime
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        task = FeedbackAsanaTask(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            asana_task_gid="1201234567890",
            asana_task_url="https://app.asana.com/0/0/1201234567890",
            asana_task_name="Some bug",
        )
        db.add(task)
        db.commit()
        task_id = task.id

        resp = client.delete("/api/v1/integrations/asana/disconnect", headers=owner_headers)
        assert resp.status_code == 200

        db.expire_all()
        preserved = db.query(FeedbackAsanaTask).filter_by(id=task_id).first()
        assert preserved is not None, "FeedbackAsanaTask rows must be preserved on disconnect"

    def test_disconnect_nonexistent_returns_404(self, client, owner_headers):
        resp = client.delete("/api/v1/integrations/asana/disconnect", headers=owner_headers)
        assert resp.status_code == 404


# ──────────────────────────── POST /test ───────────────────────────────────────

class TestTestEndpoint:
    def test_test_with_valid_token_returns_success(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post("/api/v1/integrations/asana/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_with_invalid_stored_token_returns_failure_never_500(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        # Malformed ciphertext -> decrypt_api_key raises; route must swallow it.
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token="not-a-valid-fernet-token",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            resp = client.post("/api/v1/integrations/asana/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_with_auth_error_returns_failure_never_500(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_auth_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post("/api/v1/integrations/asana/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_without_connection_returns_400(self, client, owner_headers):
        resp = client.post("/api/v1/integrations/asana/test", headers=owner_headers)
        assert resp.status_code == 400


# ──────────────────────────── GET /workspaces ──────────────────────────────────

class TestWorkspacesEndpoint:
    def test_workspaces_returns_client_data(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        mock_instance = MagicMock()
        mock_instance.get_workspaces.return_value = [
            {"gid": "1", "name": "Workspace A"},
            {"gid": "2", "name": "Workspace B"},
        ]
        mock_instance.close = MagicMock()

        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_instance):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.get("/api/v1/integrations/asana/workspaces", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body == [
            {"gid": "1", "name": "Workspace A"},
            {"gid": "2", "name": "Workspace B"},
        ]

    def test_workspaces_without_connection_returns_400(self, client, owner_headers):
        resp = client.get("/api/v1/integrations/asana/workspaces", headers=owner_headers)
        assert resp.status_code == 400

    def test_workspaces_auth_error_returns_403(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        from src.services.asana_client import AsanaAuthError
        mock_instance = MagicMock()
        mock_instance.get_workspaces.side_effect = AsanaAuthError("401 invalid token")
        mock_instance.close = MagicMock()

        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_instance):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.get("/api/v1/integrations/asana/workspaces", headers=owner_headers)
        assert resp.status_code == 403

    def test_workspaces_transient_error_returns_502(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        from src.services.asana_client import AsanaTransientError
        mock_instance = MagicMock()
        mock_instance.get_workspaces.side_effect = AsanaTransientError("503 upstream error")
        mock_instance.close = MagicMock()

        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_instance):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.get("/api/v1/integrations/asana/workspaces", headers=owner_headers)
        assert resp.status_code == 502


# ──────────────────────────── GET /projects ────────────────────────────────────

class TestProjectsEndpoint:
    def test_projects_returns_client_data(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        mock_instance = MagicMock()
        mock_instance.get_projects.return_value = [
            {"gid": "10", "name": "Project A"},
        ]
        mock_instance.close = MagicMock()

        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_instance):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.get(
                    "/api/v1/integrations/asana/projects",
                    params={"workspace_gid": "1"},
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json() == [{"gid": "10", "name": "Project A"}]
        mock_instance.get_projects.assert_called_once_with("1")

    def test_projects_without_connection_returns_400(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/asana/projects",
            params={"workspace_gid": "1"},
            headers=owner_headers,
        )
        assert resp.status_code == 400

    def test_projects_missing_workspace_gid_returns_422(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(AsanaIntegration(
            organization_id=test_organization.id,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.get("/api/v1/integrations/asana/projects", headers=owner_headers)
        assert resp.status_code == 422


# ──────────────────────────── RBAC ─────────────────────────────────────────────

class TestRBAC:
    def test_connect_member_gets_403(self, client, member_headers):
        resp = client.post(
            "/api/v1/integrations/asana/connect",
            json=_connect_payload(),
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_status_member_gets_403(self, client, member_headers):
        resp = client.get("/api/v1/integrations/asana/status", headers=member_headers)
        assert resp.status_code == 403

    def test_disconnect_member_gets_403(self, client, member_headers):
        resp = client.delete("/api/v1/integrations/asana/disconnect", headers=member_headers)
        assert resp.status_code == 403

    def test_test_member_gets_403(self, client, member_headers):
        resp = client.post("/api/v1/integrations/asana/test", headers=member_headers)
        assert resp.status_code == 403

    def test_workspaces_member_gets_403(self, client, member_headers):
        resp = client.get("/api/v1/integrations/asana/workspaces", headers=member_headers)
        assert resp.status_code == 403

    def test_projects_member_gets_403(self, client, member_headers):
        resp = client.get(
            "/api/v1/integrations/asana/projects",
            params={"workspace_gid": "1"},
            headers=member_headers,
        )
        assert resp.status_code == 403


# ──────────────────────────── Free-plan unlocked ───────────────────────────────

class TestFreePlanUnlocked:
    """asana_integration must work end-to-end for an org on the Free plan."""

    def test_connect_status_disconnect_test_all_work_on_free_plan(
        self, client, db, free_organization, free_owner_headers
    ):
        # connect
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                connect_resp = client.post(
                    "/api/v1/integrations/asana/connect",
                    json=_connect_payload(),
                    headers=free_owner_headers,
                )
        assert connect_resp.status_code == 200
        assert connect_resp.json()["connected"] is True

        # status
        status_resp = client.get("/api/v1/integrations/asana/status", headers=free_owner_headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["connected"] is True

        # test
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=asana_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                test_resp = client.post("/api/v1/integrations/asana/test", headers=free_owner_headers)
        assert test_resp.status_code == 200
        assert test_resp.json()["success"] is True

        # disconnect
        disconnect_resp = client.delete(
            "/api/v1/integrations/asana/disconnect", headers=free_owner_headers
        )
        assert disconnect_resp.status_code == 200

        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(organization_id=free_organization.id).first()
        assert row.is_active is False


def test_asana_status_route_is_registered(client, owner_headers):
    """Endpoint must be reachable — 403/200 is fine, 404 is not."""
    resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
    assert resp.status_code != 404, "Route not registered in main.py"
