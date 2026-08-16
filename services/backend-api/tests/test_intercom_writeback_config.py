"""TDD tests for the Intercom write-back config API routes (intercom-writeback R7 + S1).

Covers PATCH /writeback, the GET /status writeback extension, and the
POST /writeback/test credential probe.

Mirrors test_intercom_connection.py: IntercomClient is mocked at the route
module (`src.api.routes.intercom_integration.IntercomClient`), never touching
the network; TEST_FERNET_KEY for the Fernet encryption round-trip.

See docs/planning/intercom-writeback/config-api-routes/.
"""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.integration import Integration
from src.models.organization import Organization
from src.models.user import User

# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

ACCESS_TOKEN = "intercom-access-token-super-secret-xyz"
CLIENT_SECRET = "intercom-client-secret-abcdef"
WORKSPACE_ID = "ws_abc123"
WORKSPACE_NAME = "Acme Support"
ADMIN_ID = "admin_9001"

ROUTES_DIR = Path(__file__).resolve().parents[1] / "src" / "api" / "routes"


def intercom_client_ok(
    workspace_id=WORKSPACE_ID, workspace_name=WORKSPACE_NAME, admin_id=ADMIN_ID
):
    """An IntercomClient mock whose validate() succeeds (GET /me shape)."""
    instance = MagicMock()
    instance.validate.return_value = {
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "admin_id": admin_id,
    }
    instance.close = MagicMock()
    return instance


def intercom_client_auth_fail():
    from src.api.routes.intercom_integration import IntercomAuthError

    instance = MagicMock()
    instance.validate.side_effect = IntercomAuthError("401 unauthorized")
    instance.close = MagicMock()
    return instance


def intercom_client_transient_fail():
    from src.api.routes.intercom_integration import IntercomTransientError

    instance = MagicMock()
    instance.validate.side_effect = IntercomTransientError("503 upstream")
    instance.close = MagicMock()
    return instance


# ──────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="intercom_writeback_owner@test.com",
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
        email="intercom_writeback_member@test.com",
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


def _connect(client: TestClient, headers: dict, **overrides):
    payload = {"access_token": ACCESS_TOKEN, "client_secret": CLIENT_SECRET}
    payload.update(overrides)
    return client.post(
        "/api/v1/integrations/intercom/connect", json=payload, headers=headers
    )


def _connected(client: TestClient, headers: dict):
    with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
        "src.api.routes.intercom_integration.IntercomClient",
        return_value=intercom_client_ok(),
    ):
        response = _connect(client, headers)
    assert response.status_code == 200, response.text
    return response


def _patch_writeback(client: TestClient, headers: dict, payload: dict):
    return client.patch(
        "/api/v1/integrations/intercom/writeback",
        json=payload,
        headers=headers,
    )


# ──────────────────── AC1: PATCH /writeback contract ─────────────────────────


class TestWritebackPatch:
    def test_writeback_404_when_no_connection(
        self, client: TestClient, owner_headers: dict
    ):
        """Nothing at all — neither a token-paste nor a legacy OAuth row."""
        response = _patch_writeback(client, owner_headers, {"enabled": True})

        assert response.status_code == 404
        assert "No active Intercom integration" in response.json()["detail"]

    def test_writeback_invalid_action_returns_422(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """Literal rejection — 'close_everything' is not in the action enum."""
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)

        response = _patch_writeback(
            client, owner_headers, {"enabled": True, "action": "close_everything"}
        )

        assert response.status_code == 422
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row.writeback_enabled is False, "422 must persist nothing"

    def test_writeback_unknown_field_returns_422(
        self, client: TestClient, owner_headers: dict
    ):
        """extra='forbid' — unknown fields are rejected, not ignored."""
        response = _patch_writeback(
            client, owner_headers, {"enabled": True, "bogus_field": 1}
        )

        assert response.status_code == 422

    def test_writeback_missing_enabled_returns_422(
        self, client: TestClient, owner_headers: dict
    ):
        """`enabled` is required — a body without it is not a config change."""
        response = _patch_writeback(client, owner_headers, {"action": "note_only"})

        assert response.status_code == 422

    def test_writeback_enable_roundtrip_via_status(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)

        response = _patch_writeback(
            client, owner_headers, {"enabled": True, "action": "note_only"}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["writeback_enabled"] is True
        assert body["writeback_action"] == "note_only"

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row.writeback_enabled is True
        assert row.writeback_action == "note_only"

        # Round-trip: GET /status must report the persisted config.
        status = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert status.status_code == 200, status.text
        status_body = status.json()
        assert status_body["connected"] is True
        assert status_body["writeback_enabled"] is True
        assert status_body["writeback_action"] == "note_only"
        assert status_body["last_writeback_at"] is None
        assert status_body["last_writeback_status"] is None
        assert status_body["last_writeback_error"] is None

    def test_writeback_disable_keeps_last_writeback_history(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """Disabling never clears the status grid — history must survive."""
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        row.writeback_enabled = True
        row.writeback_action = "note_only"
        row.last_writeback_at = datetime(2026, 8, 1, 12, 0, 0)
        row.last_writeback_status = "success"
        row.last_writeback_error = "a recorded error"
        db.commit()

        response = _patch_writeback(client, owner_headers, {"enabled": False})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["writeback_enabled"] is False
        assert body["writeback_action"] == "note_only", "action persists on disable"
        assert body["last_writeback_at"] == "2026-08-01T12:00:00"
        assert body["last_writeback_status"] == "success"
        assert body["last_writeback_error"] == "a recorded error"


# ─────────────────── AC4: POST /writeback/test probe ─────────────────────────


class TestWritebackTestProbe:
    def _probe(self, client: TestClient, headers: dict):
        return client.post(
            "/api/v1/integrations/intercom/writeback/test", headers=headers
        )

    def test_writeback_test_ok_with_valid_credential(
        self, client: TestClient, owner_headers: dict
    ):
        _connected(client, owner_headers)

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = self._probe(client, owner_headers)

        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True, "reason": None}

    def test_writeback_test_auth_error_reason(
        self, client: TestClient, owner_headers: dict
    ):
        _connected(client, owner_headers)

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_auth_fail(),
        ):
            response = self._probe(client, owner_headers)

        assert response.status_code == 200
        assert response.json() == {"ok": False, "reason": "auth_error"}

    def test_writeback_test_no_admin_reason(
        self, client: TestClient, owner_headers: dict
    ):
        """A valid token whose /me carries no admin id cannot write back."""
        _connected(client, owner_headers)

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(admin_id=None),
        ):
            response = self._probe(client, owner_headers)

        assert response.status_code == 200
        assert response.json() == {"ok": False, "reason": "no_admin"}

    def test_writeback_test_missing_write_scope_from_recorded_evidence(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """Intercom /me does not report scopes; the only honest live scope
        check would mutate. So missing_write_scope comes from recorded
        evidence only — a prior real write-back that failed with that status —
        and no live check (or even client construction) happens."""
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        row.last_writeback_status = "missing_write_scope"
        db.commit()

        with patch(
            "src.api.routes.intercom_integration.IntercomClient"
        ) as mock_client:
            response = self._probe(client, owner_headers)

        assert response.status_code == 200
        assert response.json() == {"ok": False, "reason": "missing_write_scope"}
        mock_client.assert_not_called()

    def test_writeback_test_transient_error_reason(
        self, client: TestClient, owner_headers: dict
    ):
        """Upstream 5xx/network is not an auth problem — honest taxonomy."""
        _connected(client, owner_headers)

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_transient_fail(),
        ):
            response = self._probe(client, owner_headers)

        assert response.status_code == 200
        assert response.json() == {"ok": False, "reason": "transient_error"}

    def test_writeback_test_zero_mutation(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """A probe must not pollute the status grid: no row writes, no
        note/close calls, no raw httpx client."""
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)

        instance = MagicMock()
        instance.validate.return_value = {
            "workspace_id": WORKSPACE_ID,
            "workspace_name": WORKSPACE_NAME,
            "admin_id": ADMIN_ID,
        }

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        snapshot = {
            "writeback_enabled": row.writeback_enabled,
            "writeback_action": row.writeback_action,
            "last_writeback_at": row.last_writeback_at,
            "last_writeback_status": row.last_writeback_status,
            "last_writeback_error": row.last_writeback_error,
        }

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=instance,
        ) as mock_client, patch(
            "src.api.routes.intercom_integration.httpx.Client"
        ) as mock_httpx_client:
            response = self._probe(client, owner_headers)

        assert response.status_code == 200
        assert response.json() == {"ok": True, "reason": None}

        assert instance.validate.called
        assert instance.close.called
        called_names = {c[0] for c in instance.method_calls}
        assert called_names == {"validate", "close"}, (
            "probe must never call note/close endpoints on the client"
        )
        mock_client.assert_called_once()
        mock_httpx_client.assert_not_called()

        db.expire_all()
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        after = {
            "writeback_enabled": row.writeback_enabled,
            "writeback_action": row.writeback_action,
            "last_writeback_at": row.last_writeback_at,
            "last_writeback_status": row.last_writeback_status,
            "last_writeback_error": row.last_writeback_error,
        }
        assert after == snapshot, "probe must not write to the integration row"

    def test_writeback_test_404_when_no_connection(
        self, client: TestClient, owner_headers: dict
    ):
        response = self._probe(client, owner_headers)

        assert response.status_code == 404
        assert "No active Intercom integration" in response.json()["detail"]

    def test_writeback_test_409_when_legacy_oauth_only(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """Probing a legacy OAuth credential is not actionable in v1 (the
        worker task only acts on token-paste rows) — same honest 409 as PATCH."""
        db.add(
            Integration(
                organization_id=test_organization.id,
                type="intercom",
                name="Legacy OAuth",
                is_active=True,
                config={"workspace_id": WORKSPACE_ID},
            )
        )
        db.commit()

        response = self._probe(client, owner_headers)

        assert response.status_code == 409
        assert "legacy OAuth" in response.json()["detail"]


# ─────────────────────────── RBAC: members are barred ─────────────────────────


class TestWritebackConfigRBAC:
    def test_member_cannot_configure_writeback(
        self, client: TestClient, member_headers: dict
    ):
        with patch(
            "src.api.routes.intercom_integration.IntercomClient"
        ) as mock_client:
            response = _patch_writeback(
                client, member_headers, {"enabled": True}
            )

        assert response.status_code == 403
        mock_client.assert_not_called()

    def test_member_cannot_run_writeback_probe(
        self, client: TestClient, member_headers: dict
    ):
        with patch(
            "src.api.routes.intercom_integration.IntercomClient"
        ) as mock_client:
            response = client.post(
                "/api/v1/integrations/intercom/writeback/test",
                headers=member_headers,
            )

        assert response.status_code == 403
        mock_client.assert_not_called()

    def test_member_cannot_read_writeback_status(
        self, client: TestClient, member_headers: dict
    ):
        response = client.get(
            "/api/v1/integrations/intercom/status", headers=member_headers
        )
        assert response.status_code == 403


# ─────────────────── AC3: GET /status writeback extension ────────────────────


class TestWritebackStatusExtension:
    def test_status_disconnected_includes_writeback_defaults(
        self, client: TestClient, owner_headers: dict
    ):
        """A disconnected org must still expose the writeback fields, so the
        frontend can read them unconditionally."""
        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["connected"] is False
        assert body["writeback_enabled"] is False
        assert body["writeback_action"] == "note_and_close"
        assert body["last_writeback_at"] is None
        assert body["last_writeback_status"] is None
        assert body["last_writeback_error"] is None
        assert body["backlog_remaining"] is None

    def test_status_existing_fields_byte_identical(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """Characterization: every pre-existing status key keeps its exact
        value; the five writeback keys are additive."""
        from src.models.feedback import FeedbackItem
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        row.last_synced_at = datetime(2026, 7, 15, 9, 30, 0)
        row.last_sync_status = "ok"
        row.last_error = "no errors"
        row.writeback_enabled = True
        row.writeback_action = "note_and_close"
        row.last_writeback_at = datetime(2026, 7, 20, 14, 5, 0)
        row.last_writeback_status = "success"
        row.last_writeback_error = None
        row.backlog_remaining = 42
        db.commit()
        db.add(
            FeedbackItem(
                organization_id=test_organization.id,
                text="from intercom",
                source="intercom",
            )
        )
        db.commit()

        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert response.status_code == 200, response.text
        body = response.json()

        expected_existing = {
            "connected": True,
            "workspace_id": WORKSPACE_ID,
            "workspace_name": WORKSPACE_NAME,
            "token_hint": f"...{ACCESS_TOKEN[-4:]}",
            "admin_id": ADMIN_ID,
            "has_client_secret": True,
            "has_feedback_source": True,
            "last_synced_at": "2026-07-15T09:30:00",
            "last_sync_status": "ok",
            "last_error": "no errors",
            "feedback_items_ingested": 1,
        }
        for key, value in expected_existing.items():
            assert body[key] == value, f"pre-existing key {key} changed"

        assert body["writeback_enabled"] is True
        assert body["writeback_action"] == "note_and_close"
        assert body["last_writeback_at"] == "2026-07-20T14:05:00"
        assert body["last_writeback_status"] == "success"
        assert body["last_writeback_error"] is None
        assert body["backlog_remaining"] == 42

    def test_status_backlog_remaining_null_when_unset(
        self, client: TestClient, owner_headers: dict
    ):
        """A connected row that has never been synced reports no estimate."""
        _connected(client, owner_headers)
        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["backlog_remaining"] is None


# ─────────── AC2: enabling sends nothing (no HTTP, no dispatch) ───────────────


class TestWritebackEnableIsInert:
    def test_writeback_enable_sends_nothing(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """Enabling is a pure config write: no HTTP to Intercom at all."""
        from src.models.intercom_integration import IntercomIntegration

        _connected(client, owner_headers)

        with patch(
            "src.api.routes.intercom_integration.httpx.Client"
        ) as mock_httpx_client:
            response = _patch_writeback(client, owner_headers, {"enabled": True})

        assert response.status_code == 200, response.text
        mock_httpx_client.assert_not_called()

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row.writeback_enabled is True

    def test_route_module_never_dispatches(self):
        """Static guard: the router must stay Celery-free.

        There is no Celery reference in this module to mock, so the "no task
        dispatch" pin is a source inspection (test_integration_rbac_sweep.py
        precedent): if the module ever grows a dispatch path it can later be
        called silently. Dispatch belongs in the shared helper, not here.
        """
        source = (ROUTES_DIR / "intercom_integration.py").read_text(
            encoding="utf-8"
        )
        assert "send_task" not in source
        assert "celery" not in source.lower()


# ───────────── AC5: legacy-OAuth-only orgs get an honest 409 ──────────────────


class TestWritebackLegacyOAuth:
    def test_writeback_409_when_legacy_oauth_only(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """The OAuth row cannot store writeback config — a silent write-nowhere
        is the exact defect this guards. Nothing may be created or touched."""
        from src.models.intercom_integration import IntercomIntegration

        db.add(
            Integration(
                organization_id=test_organization.id,
                type="intercom",
                name="Legacy OAuth",
                is_active=True,
                config={"workspace_id": WORKSPACE_ID},
            )
        )
        db.commit()

        response = _patch_writeback(client, owner_headers, {"enabled": True})

        assert response.status_code == 409
        assert "legacy OAuth" in response.json()["detail"]

        oauth_row = (
            db.query(Integration)
            .filter(
                Integration.organization_id == test_organization.id,
                Integration.type == "intercom",
            )
            .first()
        )
        assert oauth_row is not None and oauth_row.is_active is True
        assert db.query(IntercomIntegration).count() == 0, (
            "409 must not create a token-paste row"
        )

    def test_writeback_409_wording_distinct_from_404(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """409 says 'legacy OAuth', 404 says 'no active integration' — the two
        failure modes must not be conflated by a copy/paste merge."""
        db.add(
            Integration(
                organization_id=test_organization.id,
                type="intercom",
                name="Legacy OAuth",
                is_active=True,
                config={"workspace_id": WORKSPACE_ID},
            )
        )
        db.commit()

        conflict = _patch_writeback(client, owner_headers, {"enabled": True})
        assert conflict.status_code == 409
        assert "legacy OAuth" in conflict.json()["detail"]

        # A second org with zero connection exercises the 404 wording.
        other_org = Organization(name="No Intercom At All")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)
        other_user = User(
            email="other_org_owner@test.com",
            password_hash=hash_password("pw"),
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        other_headers = {
            "Authorization": "Bearer "
            + create_access_token({
                "user_id": other_user.id,
                "organization_id": other_user.organization_id,
                "role": other_user.role,
            })
        }

        missing = _patch_writeback(client, other_headers, {"enabled": True})
        assert missing.status_code == 404
        assert "No active Intercom integration" in missing.json()["detail"]
