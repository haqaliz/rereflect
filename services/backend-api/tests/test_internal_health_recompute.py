"""Internal shared-secret health recompute endpoint (GitHub #3, option 1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth

URL = "/api/v1/internal/health/recompute"
SECRET = "test-internal-secret"


def _post(client: TestClient, secret: str | None = SECRET, **overrides):
    payload = {"org_id": 1, "customer_email": "alice@example.com"}
    payload.update(overrides)
    headers = {} if secret is None else {"X-Internal-Secret": secret}
    return client.post(URL, json=payload, headers=headers)


class TestSharedSecret:
    def test_unset_secret_fails_closed_with_503(self, client, monkeypatch):
        monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)

        response = _post(client)

        assert response.status_code == 503

    def test_wrong_secret_is_403(self, client, monkeypatch):
        monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)

        assert _post(client, secret="wrong").status_code == 403

    def test_missing_header_is_403(self, client, monkeypatch):
        monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)

        assert _post(client, secret=None).status_code == 403


class TestRecompute:
    def test_requires_a_customer_email(self, client, monkeypatch):
        monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)

        response = _post(client, customer_email="   ")

        assert response.status_code == 422

    def test_writes_the_health_row(self, client, db, test_organization, monkeypatch):
        monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)

        response = _post(
            client,
            org_id=test_organization.id,
            customer_email="alice@example.com",
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ok"
        row = (
            db.query(CustomerHealth)
            .filter_by(
                organization_id=test_organization.id,
                customer_email="alice@example.com",
            )
            .one()
        )
        assert body["health_score"] == row.health_score

    def test_updates_an_existing_health_row(self, client, db, test_organization, monkeypatch):
        monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
        db.add(
            CustomerHealth(
                organization_id=test_organization.id,
                customer_email="bob@example.com",
                health_score=1,
            )
        )
        db.commit()

        response = _post(
            client,
            org_id=test_organization.id,
            customer_email="bob@example.com",
        )

        assert response.status_code == 200, response.text
        db.expire_all()
        row = (
            db.query(CustomerHealth)
            .filter_by(
                organization_id=test_organization.id,
                customer_email="bob@example.com",
            )
            .one()
        )
        assert response.json()["health_score"] == row.health_score
        assert row.health_score != 1
