"""
Characterization tests for the Google OAuth token verifiers in
src/services/google_auth.py.

These lock down the `email_verified` enforcement (present-and-False, and
entirely-absent both reject) so that OIDC/SSO work can rely on the same
verification contract.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.services.google_auth import verify_google_token, verify_google_access_token


GOOGLE_ID_TOKEN_PAYLOAD_BASE = {
    "iss": "accounts.google.com",
    "sub": "google-user-id-12345",
    "email": "googleuser@gmail.com",
    "name": "Google User",
    "picture": "https://example.com/photo.jpg",
    "given_name": "Google",
    "family_name": "User",
}

USERINFO_PAYLOAD_BASE = {
    "sub": "google-user-id-12345",
    "email": "googleuser@gmail.com",
    "name": "Google User",
    "picture": "https://example.com/photo.jpg",
    "given_name": "Google",
    "family_name": "User",
}


class TestVerifyGoogleTokenEmailVerified:
    """Tests for the sync `verify_google_token` (ID token / id_token.verify_oauth2_token path)."""

    @patch("src.services.google_auth.GOOGLE_CLIENT_ID", "fake-client-id")
    @patch("src.services.google_auth.id_token.verify_oauth2_token")
    def test_email_verified_false_returns_none(self, mock_verify: MagicMock):
        """email_verified explicitly False -> rejected."""
        mock_verify.return_value = {**GOOGLE_ID_TOKEN_PAYLOAD_BASE, "email_verified": False}

        result = verify_google_token("some-id-token")

        assert result is None

    @patch("src.services.google_auth.GOOGLE_CLIENT_ID", "fake-client-id")
    @patch("src.services.google_auth.id_token.verify_oauth2_token")
    def test_email_verified_absent_returns_none(self, mock_verify: MagicMock):
        """email_verified key entirely absent -> rejected (uses .get(..., False))."""
        payload = dict(GOOGLE_ID_TOKEN_PAYLOAD_BASE)
        assert "email_verified" not in payload
        mock_verify.return_value = payload

        result = verify_google_token("some-id-token")

        assert result is None

    @patch("src.services.google_auth.GOOGLE_CLIENT_ID", "fake-client-id")
    @patch("src.services.google_auth.id_token.verify_oauth2_token")
    def test_email_verified_true_returns_populated_result(self, mock_verify: MagicMock):
        """email_verified True -> populated GoogleUserInfo."""
        mock_verify.return_value = {**GOOGLE_ID_TOKEN_PAYLOAD_BASE, "email_verified": True}

        result = verify_google_token("some-id-token")

        assert result is not None
        assert result["google_id"] == "google-user-id-12345"
        assert result["email"] == "googleuser@gmail.com"
        assert result["email_verified"] is True
        assert result["name"] == "Google User"


class TestVerifyGoogleAccessTokenEmailVerified:
    """Tests for the async `verify_google_access_token` (userinfo endpoint path)."""

    @staticmethod
    def _mock_httpx_get(payload: dict, status_code: int = 200):
        """Build a mock for httpx.AsyncClient.get returning the given JSON payload."""
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = payload

        async def _get(*args, **kwargs):
            return mock_response

        return _get

    @pytest.mark.asyncio
    async def test_email_verified_false_returns_none(self):
        """email_verified explicitly False -> rejected."""
        payload = {**USERINFO_PAYLOAD_BASE, "email_verified": False}
        with patch(
            "httpx.AsyncClient.get",
            new=self._mock_httpx_get(payload),
        ):
            result = await verify_google_access_token("some-access-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_email_verified_absent_returns_none(self):
        """email_verified key entirely absent -> rejected (uses .get(..., False))."""
        payload = dict(USERINFO_PAYLOAD_BASE)
        assert "email_verified" not in payload
        with patch(
            "httpx.AsyncClient.get",
            new=self._mock_httpx_get(payload),
        ):
            result = await verify_google_access_token("some-access-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_email_verified_true_returns_populated_result(self):
        """email_verified True -> populated GoogleUserInfo."""
        payload = {**USERINFO_PAYLOAD_BASE, "email_verified": True}
        with patch(
            "httpx.AsyncClient.get",
            new=self._mock_httpx_get(payload),
        ):
            result = await verify_google_access_token("some-access-token")

        assert result is not None
        assert result["google_id"] == "google-user-id-12345"
        assert result["email"] == "googleuser@gmail.com"
        assert result["email_verified"] is True
        assert result["name"] == "Google User"
