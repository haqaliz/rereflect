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
from urllib.parse import urlparse

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

    @staticmethod
    def _assert_safe_host(base_url: str) -> None:
        """
        Defense-in-depth constant scheme/host assert (mirrors
        JiraClient._assert_safe_site_url). Unlike Jira/Zendesk there is no
        per-org site_url to canonicalize/gate — the host is a compile-time
        constant — but this still asserts the invariant the client depends
        on, so an AsanaClient can never be pointed at a non-https or
        non-app.asana.com host, even if BASE_URL is ever changed or
        monkeypatched from another code path.
        """
        parsed = urlparse(base_url)
        if parsed.scheme != "https":
            raise ValueError("BASE_URL must use https")
        host = (parsed.hostname or "").lower().rstrip(".")
        if host != "app.asana.com":
            raise ValueError("BASE_URL must be the app.asana.com host")

    def __init__(self, api_token: str) -> None:
        """
        Args:
            api_token: the Asana Personal Access Token used for Bearer auth.
                Stored privately and never logged/repr'd.
        """
        self._assert_safe_host(self.BASE_URL)
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

    def _delete(self, path: str, **kwargs) -> httpx.Response:
        resp = self._client.delete(path, **kwargs)
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

    # ------------------------------------------------------------------
    # create_task (backend-create-task aspect)
    # ------------------------------------------------------------------

    def create_task(self, task: dict) -> dict:
        """
        Create an Asana task via `POST /tasks?opt_fields=permalink_url,name,gid`.

        Args:
            task: dict with `name`, `notes` (plain text, no ADF), `project_gid`,
                `workspace_gid`.

        Returns:
            dict with `gid` and `url` (the task's `permalink_url`).

        `opt_fields` is required — Asana omits `permalink_url` from the
        create response by default. If it is still absent (defensive), this
        falls back to `GET /tasks/{gid}?opt_fields=permalink_url` so the
        returned `url` is always populated.

        Raises:
            AsanaAuthError: on 401/403 (invalid/expired token or insufficient
                project permissions).
            AsanaTransientError: on 429 or 5xx.
        """
        payload = {
            "data": {
                "name": task["name"],
                "notes": task.get("notes") or "",
                "projects": [task["project_gid"]],
                "workspace": task["workspace_gid"],
            }
        }
        resp = self._post("/tasks?opt_fields=permalink_url,name,gid", json=payload)
        data = resp.json().get("data", {})
        gid = data.get("gid")
        url = data.get("permalink_url")

        if not url and gid:
            fallback = self._get(f"/tasks/{gid}", params={"opt_fields": "permalink_url"})
            url = fallback.json().get("data", {}).get("permalink_url")

        return {"gid": gid, "url": url}

    # ------------------------------------------------------------------
    # get_task (asana-client-get-task aspect)
    # ------------------------------------------------------------------

    def get_task(self, task_gid: str) -> dict:
        """
        Fetch a single task's completion state via
        `GET /tasks/{gid}?opt_fields=completed,completed_at,memberships.section.name`.

        There is no batch endpoint — Asana has no JQL-style `issue in (...)`,
        so the poller calls this once per linked task gid.

        Returns:
            dict with `completed` (bool), `completed_at` (str|None),
            `memberships` (list, `[]` when absent from the payload).

        Raises:
            AsanaAuthError: on 401/403 (invalid/expired token).
            AsanaTransientError: on 429 or 5xx. No `Retry-After` handling
                here by design — that throttle behavior lives only in the
                worker-owned client (services/worker-service/src/clients/asana.py).
            AsanaNotFoundError: on 404 (task deleted/moved).
        """
        resp = self._get(
            f"/tasks/{task_gid}",
            params={"opt_fields": "completed,completed_at,memberships.section.name"},
        )
        data = resp.json().get("data", {})
        return {
            "completed": data.get("completed"),
            "completed_at": data.get("completed_at"),
            "memberships": data.get("memberships") or [],
        }

    # ------------------------------------------------------------------
    # create_webhook / delete_webhook (asana-webhook aspect)
    # ------------------------------------------------------------------

    def create_webhook(self, resource_gid: str, target_url: str) -> dict:
        """
        Register an inbound webhook via `POST /webhooks`.

        Asana subscribes `resource_gid` (v1: a project gid -- see the
        asana-webhook aspect's R2 scope note) and will deliver a handshake
        POST (X-Hook-Secret header) to `target_url` before this call
        returns, followed by event deliveries (X-Hook-Signature) on future
        changes.

        Args:
            resource_gid: the Asana resource (project) gid to watch.
            target_url: our publicly-reachable inbound receiver URL —
                MUST already embed whatever identifier the receiver needs
                to resolve the org (see api/routes/asana_webhook.py).

        Returns:
            dict with `gid` (the Asana webhook gid — persist this to allow
            deletion later).

        Raises:
            AsanaAuthError: on 401/403.
            AsanaTransientError: on 429 or 5xx.
        """
        payload = {"data": {"resource": resource_gid, "target": target_url}}
        resp = self._post("/webhooks", json=payload)
        data = resp.json().get("data", {})
        return {"gid": data.get("gid")}

    def delete_webhook(self, webhook_gid: str) -> None:
        """
        Delete a previously-registered webhook via `DELETE /webhooks/{gid}`.

        Raises:
            AsanaAuthError: on 401/403.
            AsanaTransientError: on 429 or 5xx.
            AsanaNotFoundError: on 404 (already deleted/expired at Asana) —
                callers (the disable route) should treat this as already-clean.
        """
        self._delete(f"/webhooks/{webhook_gid}")
