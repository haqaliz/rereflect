"""
OIDC provider service: discovery, JWKS, authorize-URL construction, code
exchange, and ID-token validation for `oidc-login-flow`.

No route wiring lives here — `src/api/routes/auth.py` calls this service.

Security notes:
- The issuer host and the discovered `jwks_uri` host are each passed through
  `src.utils.ssrf.assert_host_not_ssrf` before any outbound fetch (AC2).
  Both hosts originate from operator-supplied `OidcConfig` / IdP-controlled
  discovery data, so they are treated as untrusted.
- ID-token validation is delegated to `authlib.jose` (`JsonWebToken`) rather
  than hand-rolled JWKS/signature handling: signature is verified against
  the fetched JWKS, and `iss`, `aud`, `exp`/`nbf`, and `nonce` are all
  enforced via `claims_options` + `claims.validate()`.
- Only `RS256` is accepted. This service does not negotiate algorithms with
  the IdP; if an IdP publishes only non-RS256 keys, validation will fail
  closed (`OidcValidationError`), not silently downgrade.

Caching: `discover()` and `jwks()` are each cached per-key (issuer /
jwks_uri) with a bounded TTL, so a burst of logins doesn't hammer the IdP.
Time is read through the module-level `_now()` so tests can monkeypatch it
to exercise TTL expiry without sleeping.
"""
import time
from typing import Optional
from urllib.parse import urlencode, urlparse

import httpx
from authlib.jose import JsonWebToken

from src.utils.ssrf import assert_host_not_ssrf

ALLOWED_ID_TOKEN_ALGORITHMS = ["RS256"]

_DISCOVERY_TTL_SECONDS = 3600
_JWKS_TTL_SECONDS = 3600

# Module-level caches: key -> (expires_at, data). Keyed by issuer (discovery)
# / jwks_uri (jwks) so distinct configs never collide.
_discovery_cache: dict = {}
_jwks_cache: dict = {}


def _now() -> float:
    """Wall-clock seconds. A thin wrapper so tests can monkeypatch TTL expiry."""
    return time.time()


class OidcValidationError(Exception):
    """Raised when an ID token fails signature, claims, or nonce validation."""


class OidcProvider:
    """One instance per login attempt, built from an org's enabled `OidcConfig` row."""

    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str,
        *,
        http_client: Optional[httpx.Client] = None,
    ):
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        # Injectable for tests (e.g. an httpx.Client bound to a MockTransport).
        # Not owned/closed by this class when injected.
        self._http_client = http_client

    @classmethod
    def from_config(cls, cfg) -> "OidcProvider":
        """Build a provider from an `OidcConfig` row, decrypting its client_secret."""
        from src.utils.encryption import decrypt_api_key

        return cls(
            issuer=cfg.issuer_url,
            client_id=cfg.client_id,
            client_secret=decrypt_api_key(cfg.client_secret),
        )

    # ── HTTP helpers ────────────────────────────────────────────────────

    def _get_json(self, url: str) -> dict:
        if self._http_client is not None:
            resp = self._http_client.get(url)
            resp.raise_for_status()
            return resp.json()
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()

    def _post_json(self, url: str, data: dict) -> dict:
        if self._http_client is not None:
            resp = self._http_client.post(url, data=data)
            resp.raise_for_status()
            return resp.json()
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data=data)
            resp.raise_for_status()
            return resp.json()

    # ── Discovery / JWKS (SSRF-gated, cached) ──────────────────────────

    def discover(self) -> dict:
        """Fetch (or return cached) `{issuer}/.well-known/openid-configuration`."""
        cached = _discovery_cache.get(self.issuer)
        if cached is not None:
            expires_at, data = cached
            if _now() < expires_at:
                return data

        host = urlparse(self.issuer).hostname
        assert_host_not_ssrf(host)

        data = self._get_json(f"{self.issuer}/.well-known/openid-configuration")
        _discovery_cache[self.issuer] = (_now() + _DISCOVERY_TTL_SECONDS, data)
        return data

    def jwks(self) -> dict:
        """Fetch (or return cached) the JWKS at discovery's `jwks_uri`."""
        jwks_uri = self.discover()["jwks_uri"]

        cached = _jwks_cache.get(jwks_uri)
        if cached is not None:
            expires_at, data = cached
            if _now() < expires_at:
                return data

        host = urlparse(jwks_uri).hostname
        assert_host_not_ssrf(host)

        data = self._get_json(jwks_uri)
        _jwks_cache[jwks_uri] = (_now() + _JWKS_TTL_SECONDS, data)
        return data

    # ── Authorization Code + PKCE flow ─────────────────────────────────

    def authorization_url(self, state: str, nonce: str, code_challenge: str, redirect_uri: str) -> str:
        """Build the IdP authorize URL from discovery's `authorization_endpoint`."""
        authorization_endpoint = self.discover()["authorization_endpoint"]
        params = {
            "response_type": "code",
            "scope": "openid email profile",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{authorization_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> dict:
        """POST the authorization code (+ PKCE verifier) to the token endpoint."""
        token_endpoint = self.discover()["token_endpoint"]
        return self._post_json(
            token_endpoint,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code_verifier": code_verifier,
            },
        )

    def validate_id_token(self, id_token: str, nonce: str) -> dict:
        """
        Validate an ID token's signature (vs JWKS), `iss`, `aud`, `exp`/`nbf`,
        and `nonce`. Returns the validated claims dict on success.

        Raises `OidcValidationError` on ANY failure (bad signature, wrong
        iss/aud, expired/not-yet-valid, or nonce mismatch) — never returns
        partially-validated claims.
        """
        jwt = JsonWebToken(ALLOWED_ID_TOKEN_ALGORITHMS)
        try:
            claims = jwt.decode(
                id_token,
                self.jwks(),
                claims_options={
                    "iss": {"essential": True, "value": self.issuer},
                    "aud": {"essential": True, "value": self.client_id},
                    "exp": {"essential": True},
                    "nonce": {"essential": True, "value": nonce},
                },
            )
            claims.validate()
        except Exception as exc:
            raise OidcValidationError(f"ID token validation failed: {exc}") from exc

        return dict(claims)
