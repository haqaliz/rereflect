"""Tests for the generic inbound webhook per-source secret posture.

New webhook sources get a minted `secret_token` at creation (display-once
in the create response) and fail closed on delivery: missing or wrong
`X-Webhook-Secret` → 401. Sources created before this change (no
secret_token in provider_config) keep the documented capability-URL
posture — accepted unsigned.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.feedback_source import FeedbackSource


def _create_webhook_source(
    client: TestClient,
    auth_headers: dict,
    name: str = "Generic Webhook",
) -> dict:
    response = client.post(
        "/api/v1/feedback-sources/",
        json={"source_type": "webhook", "name": name},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


class TestGenericWebhookSecretMinting:
    """POST /api/v1/feedback-sources mints a per-source secret, shown once."""

    def test_create_webhook_source_mints_display_once_secret(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Create response carries `webhook_secret`; provider_config hides it."""
        data = _create_webhook_source(client, auth_headers)

        assert data["source_type"] == "webhook"
        assert data["webhook_secret"]
        assert len(data["webhook_secret"]) >= 32
        assert "secret_token" not in data["provider_config"]

        source = db.query(FeedbackSource).filter(
            FeedbackSource.organization_id == test_organization.id,
            FeedbackSource.source_type == "webhook",
        ).first()
        assert source is not None
        assert source.provider_config["secret_token"] == data["webhook_secret"]

    def test_get_response_never_echoes_secret(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """The secret is display-once: GET must not leak it."""
        created = _create_webhook_source(client, auth_headers)
        response = client.get(
            f"/api/v1/feedback-sources/{created['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert not data.get("webhook_secret")
        assert "secret_token" not in data["provider_config"]

    def test_list_response_never_echoes_secret(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        _create_webhook_source(client, auth_headers)
        response = client.get("/api/v1/feedback-sources/", headers=auth_headers)
        assert response.status_code == 200
        webhook_sources = [
            s for s in response.json()["sources"] if s["source_type"] == "webhook"
        ]
        assert len(webhook_sources) == 1
        assert "secret_token" not in webhook_sources[0]["provider_config"]
        assert not webhook_sources[0].get("webhook_secret")

    def test_patch_response_omits_secret(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        created = _create_webhook_source(client, auth_headers)
        response = client.patch(
            f"/api/v1/feedback-sources/{created['id']}",
            json={"name": "Renamed"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret_token" not in data["provider_config"]
        assert not data.get("webhook_secret")

    def test_patch_can_set_secret_on_existing_source(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Operators can add a secret to a grandfathered source via PATCH.

        PATCH `provider_config.secret_token` passes through verbatim (the
        stored webhook_id is preserved); the response still omits it.
        """
        source = FeedbackSource(
            organization_id=test_organization.id,
            source_type="webhook",
            name="Legacy",
            provider_config={"webhook_id": "legacy-1"},
            triggers={},
            field_mapping={},
            auto_import=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        response = client.patch(
            f"/api/v1/feedback-sources/{source.id}",
            json={
                "provider_config": {
                    "webhook_id": "legacy-1",
                    "secret_token": "patched-secret-1",
                }
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider_config"]["webhook_id"] == "legacy-1"
        assert "secret_token" not in data["provider_config"]

        db.refresh(source)
        assert source.provider_config["secret_token"] == "patched-secret-1"


class TestGenericWebhookDelivery:
    """POST /api/v1/webhooks/inbound/{webhook_id} secret enforcement."""

    def _post_payload(
        self,
        client: TestClient,
        webhook_id: str,
        headers: dict | None = None,
    ):
        return client.post(
            f"/api/v1/webhooks/inbound/{webhook_id}",
            json={"text": "hello from a delivery"},
            headers=headers or {},
        )

    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-secret-ok")
    def test_correct_secret_accepted(
        self,
        mock_queue,
        client: TestClient,
        auth_headers: dict,
    ):
        created = _create_webhook_source(client, auth_headers)
        response = self._post_payload(
            client,
            created["provider_config"]["webhook_id"],
            headers={"X-Webhook-Secret": created["webhook_secret"]},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_queue.assert_called_once()

    def test_missing_secret_rejected(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        created = _create_webhook_source(client, auth_headers)
        response = self._post_payload(client, created["provider_config"]["webhook_id"])
        assert response.status_code == 401

    def test_wrong_secret_rejected(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        created = _create_webhook_source(client, auth_headers)
        response = self._post_payload(
            client,
            created["provider_config"]["webhook_id"],
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        assert response.status_code == 401

    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-grandfathered")
    def test_grandfathered_source_without_secret_accepted(
        self,
        mock_queue,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Sources created before minting (no secret_token) keep capability-URL."""
        source = FeedbackSource(
            organization_id=test_organization.id,
            source_type="webhook",
            name="Legacy Webhook",
            provider_config={"webhook_id": "legacy-webhook-id"},
            triggers={},
            field_mapping={},
            auto_import=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        response = self._post_payload(client, "legacy-webhook-id")
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_queue.assert_called_once()

    def test_token_round_trips_to_delivery(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """The exact token from the create response authenticates delivery."""
        created = _create_webhook_source(client, auth_headers)
        webhook_id = created["provider_config"]["webhook_id"]

        with patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-rt") as mock_queue:
            response = self._post_payload(
                client,
                webhook_id,
                headers={"X-Webhook-Secret": created["webhook_secret"]},
            )
        assert response.status_code == 200
        mock_queue.assert_called_once()

        response = self._post_payload(
            client,
            webhook_id,
            headers={"X-Webhook-Secret": created["webhook_secret"] + "x"},
        )
        assert response.status_code == 401
