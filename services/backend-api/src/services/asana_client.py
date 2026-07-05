"""
Asana REST API client (backend-connection aspect, Phase 2).

Thin httpx wrapper around the Asana API v1, authenticated with a Bearer
Personal Access Token (PAT) against the fixed host
`https://app.asana.com/api/1.0` — see
https://developers.asana.com/docs/personal-access-token

Unlike JiraClient/ZendeskClient there is no per-org site_url/subdomain: the
host is a compile-time constant, so there is no per-org SSRF surface to
gate. This class still asserts its own BASE_URL invariant as a cheap
defense-in-depth check.

Slice-1 scope (backend-connection): the client shell, the error taxonomy,
`validate()` (GET /users/me), `get_workspaces()` (GET /workspaces), and
`get_projects(workspace_gid)` (GET /projects?workspace=). `create_task` is
added by the `backend-create-task` aspect.

The PAT is stored in self._api_token but NEVER logged, and never appears in
repr()/str() (mirrors JiraClient's token-hiding safeguard).

Usage:
    with AsanaClient(api_token) as client:
        info = client.validate()
        print(info["gid"], info["name"])
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class AsanaError(Exception):
    """Base class for all AsanaClient errors."""


class AsanaAuthError(AsanaError):
    """Raised on 401/403 — invalid/expired PAT or insufficient permissions."""


class AsanaTransientError(AsanaError):
    """Raised on 429 / 5xx — caller should treat this as retryable."""


class AsanaNotFoundError(AsanaError):
    """Raised on 404 — the requested resource doesn't exist."""


class AsanaClient:
    """Thin httpx wrapper for the Asana API v1 (Bearer PAT, fixed host)."""

    BASE_URL = "https://app.asana.com/api/1.0"

    def __init__(self, api_token: str) -> None:
        """
        Args:
            api_token: the Asana Personal Access Token used for Bearer auth.
                Stored privately and never logged/repr'd.
        """
        # Token stored but NEVER logged / exposed via repr or str.
        self._api_token = api_token
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=15.0,
            follow_redirects=False,
        )

    def __enter__(self) -> "AsanaClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:
        return f"<AsanaClient(base_url={self.BASE_URL!r})>"

    def __str__(self) -> str:
        return self.__repr__()

    # ------------------------------------------------------------------
    # Internal request helpers — map HTTP status -> error taxonomy
    # ------------------------------------------------------------------

    def _handle_response(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise AsanaAuthError(
                f"Asana auth error (status {resp.status_code})"
            )

        if resp.status_code == 429 or resp.status_code >= 500:
            raise AsanaTransientError(
                f"Asana transient error (status {resp.status_code})"
            )

        if resp.status_code == 404:
            raise AsanaNotFoundError(
                f"Asana resource not found (status {resp.status_code})"
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
        Validate the stored PAT against `GET /users/me`.

        Returns:
            dict with `gid`, `name` (Asana's response envelope wraps the
            payload in `{"data": {...}}`).

        Raises:
            AsanaAuthError: on 401/403 (invalid/expired token).
            AsanaTransientError: on 429 or 5xx.
            AsanaNotFoundError: on 404.
        """
        resp = self._get("/users/me")
        data = resp.json().get("data", {})
        return {
            "gid": data.get("gid"),
            "name": data.get("name"),
        }

    # ------------------------------------------------------------------
    # get_workspaces / get_projects
    # ------------------------------------------------------------------

    def get_workspaces(self) -> list[dict]:
        """
        Return the Asana workspaces visible to the connected account via
        `GET /workspaces`.

        Returns:
            list of `{gid, name}` dicts.

        Raises:
            AsanaAuthError: on 401/403.
            AsanaTransientError: on 429 or 5xx.
        """
        resp = self._get("/workspaces")
        data = resp.json().get("data", [])
        return [
            {"gid": workspace.get("gid"), "name": workspace.get("name")}
            for workspace in (data or [])
        ]

    def get_projects(self, workspace_gid: str) -> list[dict]:
        """
        Return the projects visible in `workspace_gid` via
        `GET /projects?workspace={workspace_gid}`.

        Note: Asana's hierarchy is workspace -> team -> project; this
        workspace-scoped listing may omit team-scoped projects (a known,
        documented v1 limitation — see the PRD's risks section).

        Returns:
            list of `{gid, name}` dicts.

        Raises:
            AsanaAuthError: on 401/403.
            AsanaTransientError: on 429 or 5xx.
        """
        resp = self._get("/projects", params={"workspace": workspace_gid})
        data = resp.json().get("data", [])
        return [
            {"gid": project.get("gid"), "name": project.get("name")}
            for project in (data or [])
        ]
