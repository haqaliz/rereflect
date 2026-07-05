"""
Zendesk REST API client (backend-connection aspect, Phase 2).

Thin httpx wrapper around the Zendesk REST API v2, authenticated with HTTP
Basic auth using the token-auth convention (`{email}/token`, api_token) — see
https://developer.zendesk.com/api-reference/introduction/security-and-auth/#token-access

Slice-1 scope: the client shell, the error taxonomy, and `validate()`
(GET /users/me.json). Ingestion methods (ticket listing, incremental export)
are added by the separate ingestion-core aspect.

The API token is stored in self._api_token but NEVER logged, and never
appears in repr()/str() (mirrors JiraClient's / HubSpotClient's safeguard).

Usage:
    with ZendeskClient(subdomain, email, api_token) as client:
        info = client.validate()
        print(info["account_user_id"], info["display_name"])
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


class ZendeskError(Exception):
    """Base class for all ZendeskClient errors."""


class ZendeskAuthError(ZendeskError):
    """Raised on 401/403 — invalid/expired token or insufficient permissions."""


class ZendeskTransientError(ZendeskError):
    """Raised on 429 / 5xx — caller should treat this as retryable."""


class ZendeskNotFoundError(ZendeskError):
    """Raised on 404 — the requested resource doesn't exist."""


class ZendeskClient:
    """Thin httpx wrapper for the Zendesk REST API v2 (Basic auth, token access)."""

    @staticmethod
    def _assert_safe_subdomain(subdomain: str) -> None:
        """
        Defense-in-depth SSRF guard on the target subdomain (mirrors
        JiraClient._assert_safe_site_url).

        The connect route is the primary gate (it normalizes the subdomain
        and resolves + rejects private/link-local hosts); this asserts the
        invariant the client depends on so a ZendeskClient can never be
        pointed at an arbitrary host, even if constructed from another code
        path.

        String-level only (no dots/slashes/colons/whitespace, conservative
        label regex) — DNS resolution / private-IP rejection lives in the
        route to keep this class unit-testable without network I/O.
        """
        if not subdomain:
            raise ValueError("subdomain must not be empty")
        if any(ch in subdomain for ch in ("/", ":", ".", " ")) or subdomain != subdomain.strip():
            raise ValueError("subdomain must be a bare label, not a URL/host")
        if not _LABEL_RE.match(subdomain):
            raise ValueError("subdomain is not a valid label")

    def __init__(self, subdomain: str, email: str, api_token: str) -> None:
        """
        Args:
            subdomain: already-validated bare Zendesk subdomain (e.g. "acme")
                — normalization + DNS/IP SSRF checks are the connect route's
                responsibility; the client re-asserts the bare-label
                invariant as defense-in-depth.
            email: the Zendesk agent email used for Basic auth (combined
                with the "/token" suffix per Zendesk's token-auth scheme).
            api_token: the Zendesk API token used for Basic auth. Stored
                privately and never logged/repr'd.
        """
        self._assert_safe_subdomain(subdomain)
        # Token stored but NEVER logged / exposed via repr or str.
        self._subdomain = subdomain
        self._email = email
        self._api_token = api_token
        self._client = httpx.Client(
            base_url=f"https://{subdomain}.zendesk.com/api/v2",
            auth=(f"{email}/token", api_token),
            timeout=15.0,
            follow_redirects=False,
        )

    def __enter__(self) -> "ZendeskClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:
        return f"<ZendeskClient(subdomain={self._subdomain!r}, email={self._email!r})>"

    def __str__(self) -> str:
        return self.__repr__()

    # ------------------------------------------------------------------
    # Internal request helpers — map HTTP status -> error taxonomy
    # ------------------------------------------------------------------

    def _handle_response(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise ZendeskAuthError(
                f"Zendesk auth error (status {resp.status_code})"
            )

        if resp.status_code == 429 or resp.status_code >= 500:
            raise ZendeskTransientError(
                f"Zendesk transient error (status {resp.status_code})"
            )

        if resp.status_code == 404:
            raise ZendeskNotFoundError(
                f"Zendesk resource not found (status {resp.status_code})"
            )

        resp.raise_for_status()
        return resp

    def _get(self, path: str, **kwargs) -> httpx.Response:
        resp = self._client.get(path, **kwargs)
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self) -> dict:
        """
        Validate the stored credentials against `GET /users/me.json`.

        Returns:
            dict with `account_user_id` (stringified — the DB column is
            String but Zendesk's JSON `id` is a JSON number), `display_name`,
            `email`.

        Raises:
            ZendeskAuthError: on 401/403 (invalid/expired token).
            ZendeskTransientError: on 429 or 5xx.
            ZendeskNotFoundError: on 404.
        """
        resp = self._get("/users/me.json")
        data = resp.json()
        user = data.get("user", {})
        return {
            "account_user_id": str(user["id"]) if user.get("id") is not None else None,
            "display_name": user.get("name"),
            "email": user.get("email"),
        }
