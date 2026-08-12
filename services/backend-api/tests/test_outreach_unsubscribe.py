"""
Tests for outreach unsubscribe tokens + endpoint + customer opt-out PATCH
(outreach-core aspect, Phase 4).

Strict TDD: written FIRST (RED) before the implementations.
"""

import os
from unittest.mock import patch

import pytest

from src.models.customer_health import CustomerHealth


# ---------------------------------------------------------------------------
# Token helpers (AC7) — canonical backend make/verify
# ---------------------------------------------------------------------------


class TestUnsubscribeTokens:
    def test_round_trip_verify_true(self):
        from src.services.outreach_tokens import (
            make_unsubscribe_token,
            verify_unsubscribe_token,
        )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            token = make_unsubscribe_token(7, "alice@example.com")

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            assert verify_unsubscribe_token(token, 7, "alice@example.com") is True

    def test_normalizes_email_in_both_directions(self):
        from src.services.outreach_tokens import (
            make_unsubscribe_token,
            verify_unsubscribe_token,
        )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            token = make_unsubscribe_token(7, " Alice@Example.COM ")

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            assert verify_unsubscribe_token(token, 7, "alice@example.com") is True
            assert verify_unsubscribe_token(token, 7, "ALICE@EXAMPLE.COM") is True

    def test_token_for_different_email_fails(self):
        from src.services.outreach_tokens import (
            make_unsubscribe_token,
            verify_unsubscribe_token,
        )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            token = make_unsubscribe_token(7, "alice@example.com")

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            assert verify_unsubscribe_token(token, 7, "bob@example.com") is False

    def test_token_for_different_org_fails(self):
        from src.services.outreach_tokens import (
            make_unsubscribe_token,
            verify_unsubscribe_token,
        )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            token = make_unsubscribe_token(7, "alice@example.com")

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            assert verify_unsubscribe_token(token, 99, "alice@example.com") is False

    def test_tampered_digest_fails(self):
        from src.services.outreach_tokens import (
            make_unsubscribe_token,
            verify_unsubscribe_token,
        )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            token = make_unsubscribe_token(7, "alice@example.com")
            forged = token[:-4] + "beef" if not token.endswith("beef") else token[:-4] + "dead"

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            assert verify_unsubscribe_token(forged, 7, "alice@example.com") is False

    def test_garbage_token_fails(self):
        from src.services.outreach_tokens import verify_unsubscribe_token

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            assert verify_unsubscribe_token("not-a-token", 7, "alice@example.com") is False
            assert verify_unsubscribe_token("", 7, "alice@example.com") is False

    def test_make_raises_valueerror_without_key(self):
        from src.services.outreach_tokens import make_unsubscribe_token

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                make_unsubscribe_token(1, "alice@example.com")


# ---------------------------------------------------------------------------
# Unsubscribe endpoint (AC8)
# ---------------------------------------------------------------------------


def _unsub_url(client, token):
    return client.get(f"/api/v1/outreach/unsubscribe?token={token}")


class TestUnsubscribeEndpoint:
    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"})
    def test_valid_token_sets_opt_out_true(self, client, db, test_organization):
        from src.services.outreach_tokens import make_unsubscribe_token

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
            outreach_opt_out=False,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        token = make_unsubscribe_token(test_organization.id, "alice@example.com")
        response = _unsub_url(client, token)

        assert response.status_code == 200
        assert "unsubscribe" in response.text.lower()
        db.refresh(health)
        assert health.outreach_opt_out is True

    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"})
    def test_valid_token_creates_health_row_when_absent(
        self, client, db, test_organization
    ):
        from src.services.outreach_tokens import make_unsubscribe_token

        token = make_unsubscribe_token(test_organization.id, "bob@example.com")
        response = _unsub_url(client, token)

        assert response.status_code == 200
        row = (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.organization_id == test_organization.id,
                CustomerHealth.customer_email == "bob@example.com",
            )
            .first()
        )
        assert row is not None, "unsubscribe must upsert a health row when absent"
        assert row.outreach_opt_out is True

    def test_invalid_token_returns_400(self, client, db, test_organization):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
        )
        db.add(health)
        db.commit()

        response = _unsub_url(client, "not-a-token")
        assert response.status_code == 400
        db.refresh(health)
        assert health.outreach_opt_out is False

    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"})
    def test_cross_org_token_returns_400_and_touches_nothing(
        self, client, db, test_organization
    ):
        from src.services.outreach_tokens import make_unsubscribe_token

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
        )
        db.add(health)
        db.commit()

        token = make_unsubscribe_token(99999, "alice@example.com")
        response = _unsub_url(client, token)
        assert response.status_code == 400
        db.refresh(health)
        assert health.outreach_opt_out is False

    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"})
    def test_public_no_auth_required(self, client, db, test_organization):
        """GET only, no Authorization header needed."""
        from src.services.outreach_tokens import make_unsubscribe_token

        token = make_unsubscribe_token(test_organization.id, "carol@example.com")
        response = client.get(f"/api/v1/outreach/unsubscribe?token={token}")
        assert response.status_code == 200

    def test_post_returns_405(self, client):
        """GET only — POSTing to the unsubscribe URL must not opt anyone out."""
        response = client.post("/api/v1/outreach/unsubscribe?token=garbage")
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# Customer opt-out PATCH (AC9)
# ---------------------------------------------------------------------------


class TestCustomerOptOutPatch:
    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"})
    def test_admin_flips_flag_and_returns_updated_profile(
        self, client, db, test_organization, test_user, auth_headers
    ):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
        )
        db.add(health)
        db.commit()

        response = client.patch(
            f"/api/v1/customers/{health.customer_email}",
            json={"outreach_opt_out": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["customer_email"] == "alice@example.com"
        assert data["outreach_opt_out"] is True
        db.refresh(health)
        assert health.outreach_opt_out is True

    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"})
    def test_can_flip_back_to_false(self, client, db, test_organization, auth_headers):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
            outreach_opt_out=True,
        )
        db.add(health)
        db.commit()

        response = client.patch(
            f"/api/v1/customers/{health.customer_email}",
            json={"outreach_opt_out": False},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["outreach_opt_out"] is False

    def test_cross_org_email_returns_404(self, client, db, test_organization, auth_headers):
        other_org_health = CustomerHealth(
            organization_id=99999,
            customer_email="stranger@example.com",
        )
        db.add(other_org_health)
        db.commit()

        response = client.patch(
            "/api/v1/customers/stranger@example.com",
            json={"outreach_opt_out": True},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_extra_fields_returns_422(self, client, db, test_organization, auth_headers):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
        )
        db.add(health)
        db.commit()

        response = client.patch(
            f"/api/v1/customers/{health.customer_email}",
            json={"outreach_opt_out": True, "health_score": 99},
            headers=auth_headers,
        )
        assert response.status_code == 422
        db.refresh(health)
        assert health.outreach_opt_out is False

    def test_member_role_returns_403(self, client, db, test_organization, test_user):
        from src.api.auth import create_access_token
        from src.models.user import User

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="alice@example.com",
        )
        db.add(health)
        member = User(
            email="member@example.com",
            password_hash="x",
            organization_id=test_organization.id,
            role="member",
        )
        db.add(member)
        db.commit()

        token = create_access_token({
            "user_id": member.id,
            "organization_id": member.organization_id,
            "role": member.role,
        })
        response = client.patch(
            f"/api/v1/customers/{health.customer_email}",
            json={"outreach_opt_out": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        db.refresh(health)
        assert health.outreach_opt_out is False
