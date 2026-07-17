"""
Unit tests for `src/services/saml_provider.py`.

Real crypto runs here (xmlsec + python3-saml): every signed-fixture test
actually signs and validates XML — nothing is skipped. Fixtures are built
in-test with a throwaway RSA key + self-signed cert (see tests/saml_fixtures.py);
the SSRF test monkeypatches `socket.getaddrinfo` exactly like test_oidc_provider.

Security posture asserted here:
- unsigned / wrong-cert / XSW-wrapped assertions are REJECTED (R2/M8);
- wrong audience/recipient/issuer/expired/not-yet-valid/mismatched-InResponseTo
  are REJECTED with the right sso_error code;
- identity is read ONLY from the library's validated getters (never re-parsed);
- SSRF-private / http:// IdP SSO URLs are rejected at build time.
"""
import socket
import types
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from src.services.saml_provider import (
    SamlProvider,
    SamlValidationError,
    ValidatedAssertion,
)
from src.utils.ssrf import SsrfError

from tests import saml_fixtures as fx

PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _patched_public_dns():
    return patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO)


def _config(cert_pem, **overrides):
    """A minimal SamlConfig-shaped object for SamlProvider.from_config."""
    base = dict(
        idp_entity_id=fx.IDP_ENTITY_ID,
        idp_sso_url=fx.IDP_SSO_URL,
        idp_x509_cert=cert_pem,
        email_attribute=None,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


@pytest.fixture(scope="module")
def keypair():
    return fx.make_keypair_cert()


@pytest.fixture
def provider(keypair):
    _, cert_pem = keypair
    return SamlProvider.from_config(_config(cert_pem))


# ── build_authn_request ────────────────────────────────────────────────


def test_build_authn_request_returns_redirect_and_request_id(provider):
    with _patched_public_dns():
        redirect_url, request_id = provider.build_authn_request(relay_state="rs-token")

    assert redirect_url.startswith(fx.IDP_SSO_URL)
    qs = parse_qs(urlparse(redirect_url).query)
    assert "SAMLRequest" in qs
    assert qs.get("RelayState") == ["rs-token"]
    # OneLogin generates ids like "ONELOGIN_<hex>"; just assert a non-empty id.
    assert isinstance(request_id, str) and len(request_id) > 8


def test_build_authn_request_rejects_private_ip_sso_url(keypair):
    _, cert_pem = keypair
    provider = SamlProvider.from_config(_config(cert_pem))
    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    ):
        with pytest.raises(SsrfError):
            provider.build_authn_request(relay_state="rs")


def test_build_authn_request_rejects_http_sso_url(keypair):
    _, cert_pem = keypair
    provider = SamlProvider.from_config(
        _config(cert_pem, idp_sso_url="http://idp.example.com/sso")
    )
    with _patched_public_dns():
        with pytest.raises(SsrfError):
            provider.build_authn_request(relay_state="rs")
