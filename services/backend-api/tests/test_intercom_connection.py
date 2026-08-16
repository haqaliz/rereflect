"""TDD tests for the Intercom token-paste connection routes.

Covers POST /connect, GET /status, DELETE /disconnect.

Intercom is the last integration that required OAuth. Every other
BYO-credential integration (HubSpot, Zendesk, Jira, Asana) chose token-paste
because OAuth was judged awkward for self-host, and Intercom's own docs
designate an Access Token as the path for "building a private app" against
"your own Intercom workspace" -- exactly the self-host case.

Mocks IntercomClient at the route module
(`src.api.routes.intercom_integration.IntercomClient`) per the repo's
Zendesk/Jira/Linear/HubSpot test pattern -- never hits the network.

No DNS/SSRF mock is needed here, unlike Zendesk: Intercom's host is the fixed
`api.intercom.io`, so there is no per-org subdomain to resolve and no SSRF DNS
gate on this path (the same reasoning recorded for Asana's fixed
`app.asana.com`).

See docs/planning/intercom-selfhost-ingestion/token-paste-connect/.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.feedback_source import FeedbackSource
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


def intercom_client_ok(
    workspace_id=WORKSPACE_ID, workspace_name=WORKSPACE_NAME, admin_id=ADMIN_ID
):
    """An IntercomClient mock whose validate() succeeds.

    The return shape mirrors what the existing OAuth callback already parses
    out of GET https://api.intercom.io/me (`app.id_code`, `app.name`, `id`) --
    see src/api/routes/integrations.py. Do not invent a different shape here.
    """
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
        email="intercom_owner@test.com",
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
        email="intercom_member@test.com",
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


# ──────────────────────────── B1-B6: connect ──────────────────────────────────


class TestIntercomConnect:
    def test_valid_token_connects_and_resolves_workspace(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """B1 — the workspace id is what makes a source reachable at all."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["connected"] is True
        assert body["workspace_id"] == WORKSPACE_ID
        assert body["workspace_name"] == WORKSPACE_NAME

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row is not None
        assert row.workspace_id == WORKSPACE_ID
        assert row.is_active is True

    def test_secrets_are_encrypted_at_rest_and_never_returned(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """B4 — both secrets. The client_secret is collected here so a later
        aspect can verify webhook signatures per-tenant instead of against one
        global env var."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 200
        raw = response.text
        assert ACCESS_TOKEN not in raw
        assert CLIENT_SECRET not in raw

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row.access_token != ACCESS_TOKEN, "access_token stored in plaintext"
        assert row.client_secret != CLIENT_SECRET, "client_secret stored in plaintext"

    def test_invalid_token_returns_422_and_persists_nothing(
        self, client: TestClient, db: Session, owner_headers: dict
    ):
        """B2"""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_auth_fail(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 422
        assert db.query(IntercomIntegration).count() == 0

    def test_transient_upstream_returns_502_and_persists_nothing(
        self, client: TestClient, db: Session, owner_headers: dict
    ):
        """B3 — distinct from B2 so an operator can tell 'your token is wrong'
        from 'Intercom is having a bad day'."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_transient_fail(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 502
        assert db.query(IntercomIntegration).count() == 0

    def test_missing_encryption_key_returns_422_not_500(
        self, client: TestClient, db: Session, owner_headers: dict
    ):
        """B5 — a config error must be an actionable 422, not an opaque 500."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": ""}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in response.text
        assert db.query(IntercomIntegration).count() == 0

    def test_reconnect_upserts_a_single_row(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """B6"""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            assert _connect(client, owner_headers).status_code == 200
            second = _connect(
                client, owner_headers, access_token="a-rotated-token"
            )

        assert second.status_code == 200
        assert (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .count()
            == 1
        )

    def test_client_secret_is_optional(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """An operator who only wants the pull path should not be forced to
        hand over a secret nothing will read."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = client.post(
                "/api/v1/integrations/intercom/connect",
                json={"access_token": ACCESS_TOKEN},
                headers=owner_headers,
            )

        assert response.status_code == 200
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row.client_secret is None

    def test_missing_workspace_id_is_rejected(
        self, client: TestClient, db: Session, owner_headers: dict
    ):
        """A connection with no discriminator can never match a feedback source,
        so store nothing rather than a row that silently ingests nothing."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(workspace_id=None),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 422
        assert db.query(IntercomIntegration).count() == 0


# ──────────────────────── B7: the silent-ingestion trap ───────────────────────


class TestAutoProvisionedFeedbackSource:
    def test_source_is_created_with_a_truthy_trigger(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """B7 — IntercomAdapter.check_triggers returns a match ONLY when one of
        all_conversations/new_conversations/replies/ratings is truthy. A source
        provisioned with triggers={} looks connected and drops every delivery.

        Zendesk hit exactly this and had to seed new_ticket. Pinned here so the
        seeding cannot be dropped as 'redundant'.
        """
        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            assert _connect(client, owner_headers).status_code == 200

        source = (
            db.query(FeedbackSource)
            .filter(
                FeedbackSource.organization_id == test_organization.id,
                FeedbackSource.source_type == "intercom",
            )
            .first()
        )
        assert source is not None, "connect must auto-provision a feedback source"
        assert source.is_active is True
        assert source.auto_import is True
        assert source.triggers.get("new_conversations") is True, (
            "a source with no truthy trigger silently drops every delivery"
        )

    def test_reconnect_does_not_duplicate_the_source(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            _connect(client, owner_headers)
            _connect(client, owner_headers)

        assert (
            db.query(FeedbackSource)
            .filter(
                FeedbackSource.organization_id == test_organization.id,
                FeedbackSource.source_type == "intercom",
            )
            .count()
            == 1
        )


# ──────────────────────────── B8: RBAC ────────────────────────────────────────


class TestIntercomConnectionRBAC:
    """CLAUDE.md's matrix: 'Manage integrations' is Owner/Admin only.

    routes/integrations.py enforces this nowhere (DEV-TRACKING.md:422) -- the
    frontend hides the UI and the backend does not check. These new routes must
    not inherit that omission.
    """

    def test_member_cannot_connect(self, client: TestClient, member_headers: dict):
        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ) as mock_client:
            response = _connect(client, member_headers)

        assert response.status_code == 403
        # RBAC must reject before the token is ever sent upstream.
        mock_client.assert_not_called()

    def test_member_cannot_read_status(self, client: TestClient, member_headers: dict):
        response = client.get(
            "/api/v1/integrations/intercom/status", headers=member_headers
        )
        assert response.status_code == 403

    def test_member_cannot_disconnect(self, client: TestClient, member_headers: dict):
        response = client.delete(
            "/api/v1/integrations/intercom/disconnect", headers=member_headers
        )
        assert response.status_code == 403


# ─────────────────── B9: one connection per org, both paths ───────────────────


class TestOneConnectionPerOrg:
    def test_token_paste_rejected_when_oauth_already_connected(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """B9a — two credential sources for one workspace means two tenancy
        discriminators to keep correct. Reject rather than reconcile."""
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

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 409
        assert db.query(IntercomIntegration).count() == 0

    def test_inactive_oauth_row_does_not_block(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """A disconnected OAuth integration must not permanently bar the
        token-paste path."""
        from src.models.intercom_integration import IntercomIntegration

        db.add(
            Integration(
                organization_id=test_organization.id,
                type="intercom",
                name="Old OAuth",
                is_active=False,
                config={"workspace_id": WORKSPACE_ID},
            )
        )
        db.commit()

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            response = _connect(client, owner_headers)

        assert response.status_code == 200
        assert db.query(IntercomIntegration).count() == 1


# ──────────────────────── B10: status + disconnect ────────────────────────────


class TestStatusAndDisconnect:
    def test_status_reports_disconnected_when_no_row(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert response.status_code == 200
        assert response.json()["connected"] is False

    def test_status_never_leaks_secrets(
        self, client: TestClient, owner_headers: dict
    ):
        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            _connect(client, owner_headers)

        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True
        assert ACCESS_TOKEN not in response.text
        assert CLIENT_SECRET not in response.text

    def test_disconnect_soft_deletes_and_leaves_the_source(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        """B10 — connection and source lifecycle are decoupled, matching
        Zendesk (PRD 9a there): disconnecting must not destroy ingested
        history or the source's configuration."""
        from src.models.intercom_integration import IntercomIntegration

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            _connect(client, owner_headers)

        response = client.delete(
            "/api/v1/integrations/intercom/disconnect", headers=owner_headers
        )
        assert response.status_code == 200

        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == test_organization.id)
            .first()
        )
        assert row is not None, "disconnect should soft-delete, not hard-delete"
        assert row.is_active is False

        source = (
            db.query(FeedbackSource)
            .filter(
                FeedbackSource.organization_id == test_organization.id,
                FeedbackSource.source_type == "intercom",
            )
            .first()
        )
        assert source is not None, "the feedback source must survive a disconnect"


class TestIngestedItemCount:
    """S1 -- the readiness counter.

    Whether self-hosters actually use Intercom is unvalidated. A connected
    integration reporting 0 ingested items after a week is the clearest signal
    an operator can get that something is wrong (or that nobody is writing in),
    and it is the only thing that distinguishes "working" from "connected".
    """

    def test_status_reports_zero_before_anything_arrives(
        self, client: TestClient, owner_headers: dict
    ):
        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            _connect(client, owner_headers)

        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert response.status_code == 200
        assert response.json()["feedback_items_ingested"] == 0
        assert response.json()["backlog_remaining"] is None

    def test_status_counts_only_this_orgs_intercom_items(
        self, client: TestClient, db: Session, owner_headers: dict, test_organization
    ):
        from src.models.feedback import FeedbackItem

        with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}), patch(
            "src.api.routes.intercom_integration.IntercomClient",
            return_value=intercom_client_ok(),
        ):
            _connect(client, owner_headers)

        db.add_all(
            [
                FeedbackItem(
                    organization_id=test_organization.id,
                    text="from intercom",
                    source="intercom",
                ),
                # A different source in the same org must not inflate the count.
                FeedbackItem(
                    organization_id=test_organization.id,
                    text="from zendesk",
                    source="zendesk",
                ),
            ]
        )
        db.commit()

        response = client.get(
            "/api/v1/integrations/intercom/status", headers=owner_headers
        )
        assert response.json()["feedback_items_ingested"] == 1
