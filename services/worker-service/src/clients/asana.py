"""
Asana REST API client for the inbound status-sync worker task
(asana-status-sync/asana-client-get-task).

The worker cannot import backend-api, so this is a standalone mirror of
services/backend-api/src/services/asana_client.py, scoped to what the
poller needs — `get_task` only (no `validate`/`get_workspaces`/
`get_projects`/`create_task`).

Thin httpx wrapper, Bearer Personal Access Token auth against the fixed
host `https://app.asana.com/api/1.0`. Mirrors src/clients/jira.py's
structure (context manager, typed error taxonomy, token never
logged/repr'd) and throttle handling (429 -> sleep Retry-After seconds,
then raise a transient error the Celery task retries on) — the one
behavior the backend Asana client intentionally lacks.

The api_token is stored on the instance but NEVER logged, and never
appears in repr()/str().

There is no batch endpoint — Asana has no JQL-style `issue in (...)`, so
the poller calls `get_task` once per linked task gid.

Usage:
    with AsanaClient(api_token) as client:
        task = client.get_task("1300000000001")
        # -> {"completed": True, "completed_at": "...", "memberships": [...]}
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class AsanaError(Exception):
    """Base class for all worker AsanaClient errors."""


class AsanaAuthError(AsanaError):
    """Raised on 401/403 — invalid/expired PAT or insufficient permissions."""


class AsanaTransientError(AsanaError):
    """Raised on 429 (after sleeping Retry-After seconds) / 5xx — caller (Celery task) should retry."""


class AsanaNotFoundError(AsanaError):
    """Raised on 404 — the requested resource doesn't exist."""


class AsanaClient:
    """Thin httpx wrapper for the Asana API v1 (Bearer PAT, fixed host) — get_task only."""

    BASE_URL = "https://app.asana.com/api/1.0"

    @staticmethod
    def _assert_safe_host(base_url: str) -> None:
        """
        Defense-in-depth constant scheme/host assert (mirrors the backend
        AsanaClient's `_assert_safe_host`). The host is a compile-time
        constant, not a per-org value, but this still asserts the invariant
        the client depends on, so an AsanaClient can never be pointed at a
        non-https or non-app.asana.com host, even if BASE_URL is ever
        changed or monkeypatched from another code path.
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
    # Response -> error taxonomy (order matters: 429 before >=500 before
    # 401/403 before 404 before generic — mirrors clients/jira.py)
    # ------------------------------------------------------------------

    def _handle_response(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning(
                "asana_client: 429 rate limited; sleeping %ss", retry_after
            )
            time.sleep(retry_after)
            raise AsanaTransientError(
                f"Asana rate limited, retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise AsanaTransientError(f"Asana server error {resp.status_code}")

        if resp.status_code in (401, 403):
            raise AsanaAuthError(f"Asana auth error (status {resp.status_code})")

        if resp.status_code == 404:
            raise AsanaNotFoundError("Asana resource not found (status 404)")

        if resp.status_code != 200:
            raise AsanaError(f"Asana request failed with status {resp.status_code}")

        return resp

    def _get(self, path: str, **kwargs) -> httpx.Response:
        resp = self._client.get(path, **kwargs)
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # get_task
    # ------------------------------------------------------------------

    def get_task(self, task_gid: str) -> dict:
        """
        Fetch a single task's completion state via
        `GET /tasks/{gid}?opt_fields=completed,completed_at,memberships.section.name`.

        There is no batch endpoint — the poller calls this once per linked
        task gid.

        Returns:
            dict with `completed` (bool), `completed_at` (str|None),
            `memberships` (list, `[]` when absent from the payload).
            Identical shape to the backend AsanaClient.get_task.

        Raises:
            AsanaAuthError: on 401/403.
            AsanaTransientError: on 429 (after sleeping Retry-After seconds,
                default 10) or 5xx (no sleep).
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
