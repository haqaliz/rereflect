"""
Unit tests for `src/services/oidc_provider.py`.

The IdP is entirely mocked over httpx via a custom `httpx.BaseTransport`
(no live network). ID tokens are signed in-test with a locally-generated
RSA keypair; the corresponding public key is published as a JWK in the
mocked JWKS response, mirroring how a real IdP would publish it.
"""
import socket
import time
from unittest.mock import patch

import httpx
import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from cryptography.hazmat.primitives.asymmetric import rsa

from src.services import oidc_provider as oidc_provider_module
from src.services.oidc_provider import OidcProvider, OidcValidationError
from src.utils.ssrf import SsrfError

ISSUER = "https://idp.example.com"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
KID = "test-kid"

DISCOVERY_DOC = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/authorize",
    "token_endpoint": f"{ISSUER}/token",
    "jwks_uri": f"{ISSUER}/jwks",
}


@pytest.fixture(autouse=True)
def _clear_provider_caches():
    """Module-level discovery/JWKS caches must not leak between tests."""
    oidc_provider_module._discovery_cache.clear()
    oidc_provider_module._jwks_cache.clear()
    yield
    oidc_provider_module._discovery_cache.clear()
    oidc_provider_module._jwks_cache.clear()


def _rsa_keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_jwk(private_key, kid=KID):
    jwk = JsonWebKey.import_key(private_key, {"kty": "RSA", "kid": kid})
    return jwk.as_dict(is_private=False)


def _sign(private_key, claims: dict, kid=KID, alg="RS256") -> str:
    jwt = JsonWebToken([alg])
    token = jwt.encode({"alg": alg, "kid": kid}, claims, private_key)
    return token.decode() if isinstance(token, bytes) else token


def _base_claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "user-sub-1",
        "email": "person@example.com",
        "email_verified": True,
        "nonce": "expected-nonce",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return claims


class RecordingTransport(httpx.BaseTransport):
    """Routes requests by exact URL to a canned JSON response; records a
    per-URL hit count so tests can assert caching behavior (AC12)."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.call_counts: dict = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url not in self.responses:
            raise AssertionError(f"Unexpected request to {url}")
        self.call_counts[url] = self.call_counts.get(url, 0) + 1
        status, payload = self.responses[url]
        return httpx.Response(status, json=payload)


def _provider(transport: RecordingTransport) -> OidcProvider:
    client = httpx.Client(transport=transport)
    return OidcProvider(issuer=ISSUER, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http_client=client)


def _standard_transport(jwks_doc, token_response=None) -> RecordingTransport:
    responses = {
        f"{ISSUER}/.well-known/openid-configuration": (200, DISCOVERY_DOC),
        f"{ISSUER}/jwks": (200, jwks_doc),
    }
    if token_response is not None:
        responses[f"{ISSUER}/token"] = (200, token_response)
    return RecordingTransport(responses)


PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _patched_public_dns():
    """All hosts used in these tests (issuer + same-host jwks_uri) resolve publicly."""
    return patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO)


# ── AC3: ID-token validation ────────────────────────────────────────────


def test_valid_id_token_passes():
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    token = _sign(priv, _base_claims())
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        claims = provider.validate_id_token(token, nonce="expected-nonce")

    assert claims["sub"] == "user-sub-1"
    assert claims["email"] == "person@example.com"
    assert claims["email_verified"] is True


def test_wrong_issuer_rejected():
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    token = _sign(priv, _base_claims(iss="https://attacker.example.com"))
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(token, nonce="expected-nonce")


def test_wrong_audience_rejected():
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    token = _sign(priv, _base_claims(aud="some-other-client"))
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(token, nonce="expected-nonce")


def test_expired_token_rejected():
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    now = int(time.time())
    token = _sign(priv, _base_claims(iat=now - 1000, exp=now - 100))
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(token, nonce="expected-nonce")


def test_bad_signature_rejected():
    priv = _rsa_keypair()
    other_priv = _rsa_keypair()  # signed with a DIFFERENT key than published in JWKS
    jwks_doc = {"keys": [_public_jwk(priv)]}
    token = _sign(other_priv, _base_claims())
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(token, nonce="expected-nonce")


def test_mismatched_nonce_rejected():
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    token = _sign(priv, _base_claims(nonce="the-actual-nonce"))
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(token, nonce="a-different-nonce")


def test_missing_sub_claim_rejected():
    """Defense-in-depth: `sub` is OIDC-mandatory. A token validated without
    one must fail closed here too (belt-and-suspenders alongside the
    caller-side check in `oidc_callback`)."""
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    claims = _base_claims()
    del claims["sub"]
    token = _sign(priv, claims)
    provider = _provider(_standard_transport(jwks_doc))

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(token, nonce="expected-nonce")


def test_hs256_alg_confusion_token_rejected():
    """Algorithm-confusion attack: an id_token signed with HS256 (using a
    secret the attacker controls) must be rejected outright because the
    allowlist passed to `JsonWebToken` is RS256-only — the library must
    refuse to even attempt verification with a non-allowlisted algorithm,
    regardless of what secret/key material the attacker used to sign it."""
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    provider = _provider(_standard_transport(jwks_doc))

    attacker_jwt = JsonWebToken(["HS256"])
    forged = attacker_jwt.encode(
        {"alg": "HS256"}, _base_claims(), "attacker-controlled-secret"
    )
    forged = forged.decode() if isinstance(forged, bytes) else forged

    with _patched_public_dns():
        with pytest.raises(OidcValidationError):
            provider.validate_id_token(forged, nonce="expected-nonce")


# ── AC2: SSRF gate on issuer/jwks_uri hosts ─────────────────────────────


def test_discover_rejects_issuer_resolving_to_private_ip():
    provider = OidcProvider(issuer="https://internal.corp", client_id=CLIENT_ID, client_secret=CLIENT_SECRET)

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]):
        with pytest.raises(SsrfError):
            provider.discover()


def test_jwks_rejects_jwks_uri_resolving_to_private_ip():
    """Discovery itself resolves fine (public IP), but jwks_uri points at a
    DIFFERENT host that resolves privately — the jwks() call must reject it
    before fetching."""
    discovery_doc = dict(DISCOVERY_DOC, jwks_uri="https://jwks.internal.corp/jwks")
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, discovery_doc)}
    )
    provider = _provider(transport)

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "idp.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        if host == "jwks.internal.corp":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 443))]
        raise AssertionError(f"unexpected getaddrinfo host {host}")

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SsrfError):
            provider.jwks()

    # discovery succeeded (public host) but jwks fetch never happened
    assert "https://jwks.internal.corp/jwks" not in transport.call_counts


# ── AC12: discovery + JWKS cached (fetched at most once per TTL) ───────


def test_discover_is_cached_across_calls():
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, DISCOVERY_DOC)}
    )
    provider = _provider(transport)

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        provider.discover()
        provider.discover()

    assert transport.call_counts[f"{ISSUER}/.well-known/openid-configuration"] == 1


def test_jwks_is_cached_across_calls():
    priv = _rsa_keypair()
    jwks_doc = {"keys": [_public_jwk(priv)]}
    transport = _standard_transport(jwks_doc)
    provider = _provider(transport)

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        provider.jwks()
        provider.jwks()

    assert transport.call_counts[f"{ISSUER}/.well-known/openid-configuration"] == 1
    assert transport.call_counts[f"{ISSUER}/jwks"] == 1


def test_discover_refetches_after_ttl_expiry():
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, DISCOVERY_DOC)}
    )
    provider = _provider(transport)

    real_now = oidc_provider_module._now()
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        with patch.object(oidc_provider_module, "_now", return_value=real_now):
            provider.discover()
        with patch.object(oidc_provider_module, "_now", return_value=real_now + 7200):
            provider.discover()

    assert transport.call_counts[f"{ISSUER}/.well-known/openid-configuration"] == 2


# ── authorization_url / exchange_code ───────────────────────────────────


def test_authorization_url_contains_expected_params():
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, DISCOVERY_DOC)}
    )
    provider = _provider(transport)

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        url = provider.authorization_url(
            state="signed-state-value",
            nonce="a-nonce",
            code_challenge="a-code-challenge",
            redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
        )

    assert url.startswith(f"{ISSUER}/authorize?")
    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url or "scope=openid%20email%20profile" in url
    assert f"client_id={CLIENT_ID}" in url
    assert "state=signed-state-value" in url
    assert "nonce=a-nonce" in url
    assert "code_challenge=a-code-challenge" in url
    assert "code_challenge_method=S256" in url


def test_exchange_code_posts_expected_params_and_returns_tokens():
    token_response = {"id_token": "fake-id-token", "access_token": "fake-access-token"}
    transport = _standard_transport({"keys": []}, token_response=token_response)
    provider = _provider(transport)

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        result = provider.exchange_code(
            code="auth-code-123",
            code_verifier="verifier-abc",
            redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
        )

    assert result == token_response
    assert transport.call_counts[f"{ISSUER}/token"] == 1


# ── Security-review follow-up: SSRF gate + https-only + issuer-containment
#    on token_endpoint (and authorization_endpoint), not just issuer/jwks_uri
# ─────────────────────────────────────────────────────────────────────────


def test_exchange_code_rejects_token_endpoint_resolving_to_private_ip():
    """token_endpoint from discovery points at a host that resolves to a
    private IP — must be rejected before the client_secret is ever POSTed."""
    discovery_doc = dict(DISCOVERY_DOC, token_endpoint="https://token.internal.corp/token")
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, discovery_doc)}
    )
    provider = _provider(transport)

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "idp.example.com":
            return PUBLIC_ADDRINFO
        if host == "token.internal.corp":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 443))]
        raise AssertionError(f"unexpected getaddrinfo host {host}")

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SsrfError):
            provider.exchange_code(
                code="auth-code-123",
                code_verifier="verifier-abc",
                redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
            )

    assert "https://token.internal.corp/token" not in transport.call_counts


def test_exchange_code_rejects_http_scheme_token_endpoint():
    """token_endpoint uses plain http:// — https-only must reject it."""
    discovery_doc = dict(DISCOVERY_DOC, token_endpoint=f"http://idp.example.com/token")
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, discovery_doc)}
    )
    provider = _provider(transport)

    with _patched_public_dns():
        with pytest.raises(SsrfError):
            provider.exchange_code(
                code="auth-code-123",
                code_verifier="verifier-abc",
                redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
            )

    assert "http://idp.example.com/token" not in transport.call_counts


def test_exchange_code_rejects_token_endpoint_on_different_public_host():
    """token_endpoint points at a DIFFERENT (but publicly-resolving) host than
    the issuer — issuer-containment must reject it so client_secret is never
    sent cross-host, even though the SSRF host check alone would pass."""
    discovery_doc = dict(DISCOVERY_DOC, token_endpoint="https://evil.attacker.com/token")
    transport = RecordingTransport(
        {
            f"{ISSUER}/.well-known/openid-configuration": (200, discovery_doc),
            "https://evil.attacker.com/token": (200, {"id_token": "x"}),
        }
    )
    provider = _provider(transport)

    def fake_getaddrinfo(host, *args, **kwargs):
        # Both hosts resolve PUBLICLY — the attack only works because the
        # SSRF-only check would let this through.
        return PUBLIC_ADDRINFO

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SsrfError):
            provider.exchange_code(
                code="auth-code-123",
                code_verifier="verifier-abc",
                redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
            )

    # The POST (which carries client_secret) must never have been sent.
    assert "https://evil.attacker.com/token" not in transport.call_counts


def test_exchange_code_allows_token_endpoint_on_issuer_subdomain():
    """token_endpoint on a subdomain of the issuer host (e.g. issuer
    `https://example.com`, token_endpoint `https://login.example.com/token`)
    is ALLOWED — issuer-containment permits subdomains of the issuer host."""
    sub_issuer = "https://example.com"
    discovery_doc = {
        "issuer": sub_issuer,
        "authorization_endpoint": f"{sub_issuer}/authorize",
        "token_endpoint": "https://login.example.com/token",
        "jwks_uri": f"{sub_issuer}/jwks",
    }
    token_response = {"id_token": "fake-id-token", "access_token": "fake-access-token"}
    transport = RecordingTransport(
        {
            f"{sub_issuer}/.well-known/openid-configuration": (200, discovery_doc),
            "https://login.example.com/token": (200, token_response),
        }
    )
    client = httpx.Client(transport=transport)
    provider = OidcProvider(
        issuer=sub_issuer, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http_client=client
    )

    def fake_getaddrinfo(host, *args, **kwargs):
        return PUBLIC_ADDRINFO

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        result = provider.exchange_code(
            code="auth-code-123",
            code_verifier="verifier-abc",
            redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
        )

    assert result == token_response
    assert transport.call_counts["https://login.example.com/token"] == 1


def test_authorization_url_rejects_authorization_endpoint_on_different_public_host():
    """Same issuer-containment rule applies to authorization_endpoint."""
    discovery_doc = dict(DISCOVERY_DOC, authorization_endpoint="https://evil.attacker.com/authorize")
    transport = RecordingTransport(
        {f"{ISSUER}/.well-known/openid-configuration": (200, discovery_doc)}
    )
    provider = _provider(transport)

    def fake_getaddrinfo(host, *args, **kwargs):
        return PUBLIC_ADDRINFO

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(SsrfError):
            provider.authorization_url(
                state="signed-state-value",
                nonce="a-nonce",
                code_challenge="a-code-challenge",
                redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
            )
