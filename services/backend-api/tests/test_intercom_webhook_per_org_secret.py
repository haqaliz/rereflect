"""Per-tenant Intercom webhook signature verification.

The 1.0.0 changelog recorded this as a limitation that could not be fixed:

    "A valid signature cannot identify a tenant here. INTERCOM_CLIENT_SECRET is
     a single global env var, unlike Zendesk's per-org webhook_secret which is
     looked up *by* the discriminator."

That was true while OAuth was the only connect path. It stopped being true with
token-paste: obtaining an Intercom Access Token requires creating a Developer
Hub app, and that app's Client Secret is exactly the key Intercom signs
X-Hub-Signature with. Storing it per-org makes verification per-tenant.

THE ORDERING PROBLEM, and why parsing before verifying is still fail-closed.
The route must know which org an event is for in order to pick a secret, but
`app_id` lives in the not-yet-verified body. So the body is parsed FIRST, and
`app_id` is used *only* to select candidate secrets. A forged app_id therefore
selects a secret whose HMAC will not validate the attacker's body, and the
request is rejected exactly as before. Nothing is trusted from the payload
except which key to try.

See docs/planning/intercom-selfhost-ingestion/webhook-per-org-secret/.
"""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, patch

from src.models.intercom_integration import IntercomIntegration
from src.models.organization import Organization
from src.utils.encryption import encrypt_api_key

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

ORG_A_WORKSPACE = "ws_org_a"
ORG_A_SECRET = "org-a-client-secret"
ORG_B_WORKSPACE = "ws_org_b"
ORG_B_SECRET = "org-b-client-secret"
GLOBAL_SECRET = "global-oauth-client-secret"


def _sign(body: bytes, secret: str) -> str:
    return "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()


def _payload(workspace_id=ORG_A_WORKSPACE, conv_id="conv_1"):
    return {
        "topic": "conversation.user.created",
        "app_id": workspace_id,
        "data": {
            "item": {
                "type": "conversation",
                "id": conv_id,
                "conversation_message": {
                    "body": "<p>The export keeps timing out on large reports.</p>",
                    "author": {"type": "user", "id": "c1", "email": "d@example.com"},
                },
            }
        },
    }


def _make_org_with_secret(db: Session, name, workspace_id, secret):
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)

    with patch.dict("os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        encrypted = encrypt_api_key(secret)

    from datetime import datetime

    row = IntercomIntegration(
        organization_id=org.id,
        access_token="enc:token",
        client_secret=encrypted,
        workspace_id=workspace_id,
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return org


def _post(client: TestClient, payload: dict, signature: str):
    body = json.dumps(payload).encode()
    return client.post(
        "/api/v1/webhooks/intercom/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature": signature},
    )


@pytest.fixture
def _queue():
    with patch(
        "src.api.routes.source_webhooks.queue_source_event", return_value="task-1"
    ) as m:
        yield m


class TestPerOrgSecret:
    def test_org_secret_verifies_when_no_global_secret_is_set(
        self, client: TestClient, db: Session, _queue
    ):
        """The case that was impossible before: a self-hoster with no OAuth app
        and therefore no INTERCOM_CLIENT_SECRET at all."""
        _make_org_with_secret(db, "Org A", ORG_A_WORKSPACE, ORG_A_SECRET)
        payload = _payload()
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", ""):
            response = _post(client, payload, _sign(body, ORG_A_SECRET))

        assert response.status_code == 200
        _queue.assert_called_once()

    def test_global_secret_still_verifies_for_oauth_orgs(
        self, client: TestClient, db: Session, _queue
    ):
        """D4 keeps both credential paths working. An OAuth org has no
        IntercomIntegration row and must keep verifying against the env var."""
        payload = _payload(workspace_id="ws_oauth_org")
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch(
            "src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", GLOBAL_SECRET
        ):
            response = _post(client, payload, _sign(body, GLOBAL_SECRET))

        assert response.status_code == 200

    def test_wrong_signature_is_rejected(self, client: TestClient, db: Session, _queue):
        _make_org_with_secret(db, "Org A", ORG_A_WORKSPACE, ORG_A_SECRET)
        payload = _payload()
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", ""):
            response = _post(client, payload, _sign(body, "not-the-secret"))

        assert response.status_code == 401
        _queue.assert_not_called()

    def test_no_candidate_secret_fails_closed(
        self, client: TestClient, db: Session, _queue
    ):
        """Unknown workspace and no global secret -- there is nothing to verify
        against, so reject. This is the property
        test_webhook_verifiers_fail_closed.py enforces globally."""
        payload = _payload(workspace_id="ws_nobody")
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", ""):
            response = _post(client, payload, _sign(body, ORG_A_SECRET))

        assert response.status_code == 401
        _queue.assert_not_called()

    def test_forged_app_id_cannot_borrow_another_orgs_trust(
        self, client: TestClient, db: Session, _queue
    ):
        """THE test for the ordering problem.

        An attacker who knows org B's workspace id puts it in the payload to
        select org B's secret. They still cannot sign the body with it, so the
        HMAC fails and the request is rejected. Parsing before verifying is
        therefore safe: app_id chooses which key to try, never whether to trust.
        """
        _make_org_with_secret(db, "Org A", ORG_A_WORKSPACE, ORG_A_SECRET)
        _make_org_with_secret(db, "Org B", ORG_B_WORKSPACE, ORG_B_SECRET)

        payload = _payload(workspace_id=ORG_B_WORKSPACE)
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", ""):
            # signed with the secret the attacker actually has
            response = _post(client, payload, _sign(body, ORG_A_SECRET))

        assert response.status_code == 401
        _queue.assert_not_called()

    def test_inactive_integration_secret_is_not_a_candidate(
        self, client: TestClient, db: Session, _queue
    ):
        """Disconnecting must actually stop accepting deliveries."""
        org = _make_org_with_secret(db, "Org A", ORG_A_WORKSPACE, ORG_A_SECRET)
        row = (
            db.query(IntercomIntegration)
            .filter(IntercomIntegration.organization_id == org.id)
            .first()
        )
        row.is_active = False
        db.commit()

        payload = _payload()
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", ""):
            response = _post(client, payload, _sign(body, ORG_A_SECRET))

        assert response.status_code == 401


class TestBodyHandling:
    def test_malformed_json_returns_400_not_500(
        self, client: TestClient, db: Session, _queue
    ):
        """The body is parsed before verification now, so a parse failure must
        be handled explicitly rather than escaping as a 500."""
        body = b"{not json"
        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", GLOBAL_SECRET):
            response = client.post(
                "/api/v1/webhooks/intercom/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature": _sign(body, GLOBAL_SECRET),
                },
            )

        assert response.status_code == 400
        _queue.assert_not_called()

    def test_oversized_body_is_rejected(self, client: TestClient, db: Session, _queue):
        """Parsing before verifying means an unauthenticated caller can make us
        parse JSON, so the body must be bounded."""
        payload = _payload()
        payload["data"]["item"]["padding"] = "x" * (2 * 1024 * 1024)
        body = json.dumps(payload).encode()

        with patch.dict(
            "os.environ", {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}
        ), patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", GLOBAL_SECRET):
            response = client.post(
                "/api/v1/webhooks/intercom/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature": _sign(body, GLOBAL_SECRET),
                },
            )

        assert response.status_code == 413
        _queue.assert_not_called()
