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
- SSRF-private / http:// IdP SSO URLs are rejected at build time;
- the ±60s skew supplement tightens the library's native 300s drift and bites.
"""
import base64
import socket
import types
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from onelogin.saml2.constants import OneLogin_Saml2_Constants

from src.services.saml_provider import (
    SamlProvider,
    SamlValidationError,
    ValidatedAssertion,
)
from src.utils.ssrf import SsrfError

from tests import saml_fixtures as fx

PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
NAMEID_EMAIL = OneLogin_Saml2_Constants.NAMEID_EMAIL_ADDRESS
NAMEID_UNSPEC = OneLogin_Saml2_Constants.NAMEID_UNSPECIFIED


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
def backend_https(monkeypatch):
    """SP entityId/ACS derive from BACKEND_URL; the library forces https on the
    ACS current-url, so the fixtures (Destination/Recipient) are https too."""
    monkeypatch.setenv("BACKEND_URL", "https://localhost:8000")


@pytest.fixture
def provider(keypair, backend_https):
    _, cert_pem = keypair
    return SamlProvider.from_config(_config(cert_pem))


def _validate(provider, b64, in_response_to=fx.DEFAULT_IN_RESPONSE_TO):
    return provider.validate_response(
        b64, expected_in_response_to=in_response_to, acs_url=provider.acs_url
    )


# ── build_authn_request ────────────────────────────────────────────────


def test_build_authn_request_returns_redirect_and_request_id(keypair):
    _, cert_pem = keypair
    provider = SamlProvider.from_config(_config(cert_pem))
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


# ── validate_response: happy path ──────────────────────────────────────


def test_valid_signed_assertion_passes(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(key, cert, attributes={"email": ["User@Example.com"]})
    va = _validate(provider, b64)
    assert isinstance(va, ValidatedAssertion)
    assert va.subject == fx.DEFAULT_NAMEID
    assert va.email == "user@example.com"  # lowercased


# ── validate_response: signature rejection paths (R2 / M8) ─────────────


def test_unsigned_assertion_rejected(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(key, cert, sign=False, attributes={"email": ["u@example.com"]})
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "assertion"


def test_wrong_cert_signature_rejected(provider, keypair):
    key, cert = keypair
    other_key, other_cert = fx.make_keypair_cert("attacker")
    # Signed with a DIFFERENT key than the provider's configured cert.
    b64 = fx.make_signed_response(
        key, cert, sign_key_pem=other_key, sign_cert_pem=other_cert,
        attributes={"email": ["u@example.com"]},
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "signature"


def test_xsw_wrapped_assertion_rejected_and_forged_subject_never_surfaces(provider, keypair):
    """XML Signature Wrapping: a forged, UNSIGNED assertion (attacker NameID) is
    wrapped around a legitimately-signed one. A naive parser that reads the first
    NameID would return the attacker; the delegated validator must reject the
    document outright and NEVER yield the forged subject."""
    key, cert = keypair
    b64 = fx.make_signed_response(key, cert, xsw=True, attributes={"email": ["u@example.com"]})

    # The fixture genuinely embeds the attack: the attacker NameID is present in
    # the raw XML (so a naive parse WOULD pick it up).
    raw = base64.b64decode(b64).decode()
    assert "attacker@evil.example.com" in raw

    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code in {"assertion", "signature"}
    # And the forged subject must never have been returned.
    assert "attacker" not in str(ei.value).lower() or ei.value.code in {"assertion", "signature"}


def test_response_signed_but_assertion_unsigned_rejected(provider, keypair):
    """Policy: require a signed ASSERTION, not merely a signed Response. A
    message whose Response is signed but whose Assertion is not must be
    rejected — otherwise an attacker who can sign a wrapper Response (or strip
    the assertion signature) would slip an unsigned assertion through."""
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert, sign=False, sign_response=True, attributes={"email": ["u@example.com"]}
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "assertion"


def test_assertion_signature_requirement_is_load_bearing(keypair, backend_https):
    """Prove the unsigned-assertion rejection actually BITES: the SAME
    response-signed / assertion-unsigned message that the strict config rejects
    is ACCEPTED once `wantAssertionsSigned` is flipped off. That flag — not some
    incidental fixture defect — is what stops the unsigned/XSW assertion."""
    key, cert = keypair
    provider = SamlProvider.from_config(_config(cert))
    b64 = fx.make_signed_response(
        key, cert, sign=False, sign_response=True, attributes={"email": ["u@example.com"]}
    )

    # Strict (real) config rejects it because the assertion is unsigned.
    with pytest.raises(SamlValidationError) as ei:
        provider.validate_response(
            b64, expected_in_response_to=fx.DEFAULT_IN_RESPONSE_TO, acs_url=provider.acs_url
        )
    assert ei.value.code == "assertion"

    # Flip wantAssertionsSigned off (permissive misconfig) → now accepted.
    settings = provider._build_settings()
    settings["security"]["wantAssertionsSigned"] = False
    provider._settings_cache = settings
    va = provider.validate_response(
        b64, expected_in_response_to=fx.DEFAULT_IN_RESPONSE_TO, acs_url=provider.acs_url
    )
    assert va.subject == fx.DEFAULT_NAMEID  # the hole the strict flag closes


# ── validate_response: condition rejection paths ───────────────────────


def test_wrong_audience_rejected(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(key, cert, audience="https://wrong-sp.example.com")
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "audience"


def test_wrong_recipient_rejected(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert,
        recipient="https://localhost:8000/api/v1/auth/saml/WRONG",
        destination="https://localhost:8000/api/v1/auth/saml/WRONG",
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "recipient"


def test_wrong_issuer_rejected(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(key, cert, issuer="https://evil-idp.example.com/metadata")
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    # No dedicated issuer sso_error code exists — folds into `assertion`.
    assert ei.value.code == "assertion"


def test_mismatched_in_response_to_rejected(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(key, cert)  # InResponseTo = DEFAULT
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64, in_response_to="_some-other-request-id")
    assert ei.value.code == "unsolicited"


def test_expired_assertion_rejected(provider, keypair):
    key, cert = keypair
    # Well beyond the library's 300s drift AND our ±60s supplement.
    b64 = fx.make_signed_response(
        key, cert, not_before_delta_seconds=-1200, not_on_or_after_delta_seconds=-600
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "expired"


def test_not_yet_valid_assertion_rejected(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert, not_before_delta_seconds=600, not_on_or_after_delta_seconds=1200
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "expired"


def test_null_subject_rejected(provider, keypair):
    """Account-takeover guard: an assertion with no NameID is rejected before
    any identity is returned (kept from the OIDC `sub` guard)."""
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert, include_subject=False, attributes={"email": ["u@example.com"]}
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "assertion"


# ── ±60s clock-skew supplement (tightens the library's native 300s drift) ─


def test_skew_within_60s_still_passes(provider, keypair):
    """Conditions expired 30s ago (within ±60s) while the strict SC window is
    still open → accepted (tolerance)."""
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert,
        not_before_delta_seconds=-120,
        not_on_or_after_delta_seconds=-30,       # Conditions expired 30s ago
        sc_not_on_or_after_delta_seconds=3600,   # SubjectConfirmation still valid
        attributes={"email": ["u@example.com"]},
    )
    va = _validate(provider, b64)
    assert va.subject == fx.DEFAULT_NAMEID


def test_skew_beyond_60s_rejected(provider, keypair):
    """Conditions expired 120s ago (beyond ±60s) — the library's native 300s
    drift would accept it, but our supplement tightens to ±60s and rejects."""
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert,
        not_before_delta_seconds=-240,
        not_on_or_after_delta_seconds=-120,      # Conditions expired 120s ago
        sc_not_on_or_after_delta_seconds=3600,   # SubjectConfirmation still valid
        attributes={"email": ["u@example.com"]},
    )
    with pytest.raises(SamlValidationError) as ei:
        _validate(provider, b64)
    assert ei.value.code == "expired"
    assert "skew" in ei.value.detail.lower()  # our supplement, not the library


# ── email extraction chain ─────────────────────────────────────────────


def test_email_from_nameid_emailaddress_format(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert, name_id="Alice@Example.com", name_id_format=NAMEID_EMAIL
    )
    va = _validate(provider, b64)
    assert va.subject == "Alice@Example.com"
    assert va.email == "alice@example.com"


def test_email_from_configured_attribute(keypair, backend_https):
    key, cert = keypair
    provider = SamlProvider.from_config(_config(cert, email_attribute="mail"))
    b64 = fx.make_signed_response(
        key, cert,
        name_id="opaque-subject-123",
        name_id_format=NAMEID_UNSPEC,
        attributes={"mail": ["Bob@Example.com"], "email": ["ignored@example.com"]},
    )
    va = provider.validate_response(
        b64, expected_in_response_to=fx.DEFAULT_IN_RESPONSE_TO, acs_url=provider.acs_url
    )
    assert va.subject == "opaque-subject-123"
    assert va.email == "bob@example.com"  # configured attr wins over default chain


def test_email_from_default_chain_urn_oid(provider, keypair):
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert,
        name_id="opaque-subject-456",
        name_id_format=NAMEID_UNSPEC,
        attributes={"urn:oid:0.9.2342.19200300.100.1.3": ["Carol@Example.com"]},
    )
    va = _validate(provider, b64)
    assert va.subject == "opaque-subject-456"
    assert va.email == "carol@example.com"


def test_no_email_when_none_present(provider, keypair):
    """A missing email is not fatal in the provider (the route decides) —
    email is None, subject still returned."""
    key, cert = keypair
    b64 = fx.make_signed_response(
        key, cert, name_id="opaque-subject-789", name_id_format=NAMEID_UNSPEC,
        attributes={"displayName": ["No Email Here"]},
    )
    va = _validate(provider, b64)
    assert va.subject == "opaque-subject-789"
    assert va.email is None
