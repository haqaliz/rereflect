"""
Jira Cloud REST API client (backend-connection aspect, Phase 2).

Thin httpx wrapper around the Jira Cloud REST API v3, authenticated with
HTTP Basic auth (email + Atlassian API token) — see
https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/

Slice-1 scope: the client shell, the error taxonomy, and `validate()`
(GET /myself). `get_projects` / `get_issue_types` / `create_issue` are added
by the `backend-create-issue` aspect.

The API token is stored in self._api_token but NEVER logged, and never
appears in repr()/str() (mirrors HubSpotClient's R3 safeguard in
services/worker-service/src/clients/hubspot.py).

Usage:
    with JiraClient(site_url, email, api_token) as client:
        info = client.validate()
        print(info["account_id"], info["display_name"])
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class JiraError(Exception):
    """Base class for all JiraClient errors."""


class JiraAuthError(JiraError):
    """Raised on 401/403 — invalid/expired token or insufficient permissions."""


class JiraTransientError(JiraError):
    """Raised on 429 / 5xx — caller should treat this as retryable."""


class JiraNotFoundError(JiraError):
    """Raised on 404 — the requested resource doesn't exist."""


class JiraClient:
    """Thin httpx wrapper for the Jira Cloud REST API v3 (Basic auth)."""

    API_PATH = "/rest/api/3"

    def __init__(self, site_url: str, email: str, api_token: str) -> None:
        """
        Args:
            site_url: already-canonicalized `https://{site}.atlassian.net`
                (normalization is the connect route's responsibility, not
                the client's).
            email: the Atlassian account email used for Basic auth.
            api_token: the Atlassian API token used for Basic auth. Stored
                privately and never logged/repr'd.
        """
        # Token stored but NEVER logged / exposed via repr or str.
        self._site_url = site_url
        self._email = email
        self._api_token = api_token
        self._client = httpx.Client(
            base_url=f"{site_url}{self.API_PATH}",
            auth=(email, api_token),
            timeout=15.0,
        )

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:
        return f"<JiraClient(site_url={self._site_url!r}, email={self._email!r})>"

    def __str__(self) -> str:
        return self.__repr__()

    # ------------------------------------------------------------------
    # Internal request helpers — map HTTP status -> error taxonomy
    # ------------------------------------------------------------------

    def _handle_response(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise JiraAuthError(
                f"Jira auth error (status {resp.status_code})"
            )

        if resp.status_code == 429 or resp.status_code >= 500:
            raise JiraTransientError(
                f"Jira transient error (status {resp.status_code})"
            )

        if resp.status_code == 404:
            raise JiraNotFoundError(
                f"Jira resource not found (status {resp.status_code})"
            )

        resp.raise_for_status()
        return resp

    def _get(self, path: str, **kwargs) -> httpx.Response:
        resp = self._client.get(path, **kwargs)
        return self._handle_response(resp)

    def _post(self, path: str, json: dict = None, **kwargs) -> httpx.Response:
        resp = self._client.post(path, json=json, **kwargs)
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self) -> dict:
        """
        Validate the stored credentials against `GET /myself`.

        Returns:
            dict with `account_id`, `display_name`, `email` (snake_case,
            translated from Atlassian's `accountId`/`displayName`/
            `emailAddress`).

        Raises:
            JiraAuthError: on 401/403 (invalid/expired token).
            JiraTransientError: on 429 or 5xx.
            JiraNotFoundError: on 404.
        """
        resp = self._get("/myself")
        data = resp.json()
        return {
            "account_id": data.get("accountId"),
            "display_name": data.get("displayName"),
            "email": data.get("emailAddress"),
        }
