"""
Jira Cloud REST API client for the inbound status-sync worker task
(jira-status-sync/inbound-status-sync, Phase 4).

The worker cannot import backend-api, so this is a standalone mirror of
services/backend-api/src/services/jira_client.py, scoped to what the
poller needs — `search_issues` only (no `validate`/`create_issue`/etc).

Thin httpx wrapper, HTTP Basic auth (email, Atlassian API token), base
`{site_url}/rest/api/3`, 15s timeout. Mirrors src/clients/zendesk.py's
structure (context manager, typed error taxonomy, token never
logged/repr'd) and throttle handling (429 -> sleep Retry-After seconds,
then raise a transient error the Celery task retries on).

R3: the api_token is stored on the instance but NEVER logged, and never
    appears in repr()/str().

Usage:
    with JiraClient(site_url, email, api_token) as client:
        statuses = client.search_issues(["ENG-1", "ENG-2"])
        # -> {"ENG-1": {"name": "Done", "category": "done"}, ...}
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class JiraError(Exception):
    """Base class for all JiraClient errors."""


class JiraAuthError(JiraError):
    """Raised on 401/403 — invalid/expired token or insufficient permissions."""


class JiraTransientError(JiraError):
    """Raised on 429 (after sleeping Retry-After seconds) / 5xx — caller (Celery task) should retry."""


class JiraNotFoundError(JiraError):
    """Raised on 404 — the requested resource doesn't exist."""


class JiraClient:
    """Thin httpx wrapper for the Jira Cloud REST API v3 (Basic auth) — search_issues only."""

    API_PATH = "/rest/api/3"
    _SEARCH_PATH = "/search"

    # Jira Cloud JQL search caps results per page; page through with
    # startAt/maxResults until every issue has been collected.
    _SEARCH_PAGE_SIZE = 100

    # Cap the number of issue keys embedded in a single JQL `issue in (...)`
    # clause per call — callers with more keys are chunked internally and
    # the per-chunk results are merged.
    _SEARCH_BATCH_SIZE = 50

    def __init__(self, site_url: str, email: str, api_token: str) -> None:
        # R3: token stored but NEVER logged / exposed via repr or str.
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
    # Response -> error taxonomy
    # ------------------------------------------------------------------

    def _handle_response(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning(
                "jira_client: 429 rate limited; sleeping %ss", retry_after
            )
            time.sleep(retry_after)
            raise JiraTransientError(
                f"Jira rate limited, retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise JiraTransientError(f"Jira server error {resp.status_code}")

        if resp.status_code in (401, 403):
            raise JiraAuthError(f"Jira auth error (status {resp.status_code})")

        if resp.status_code == 404:
            raise JiraNotFoundError("Jira resource not found (status 404)")

        if resp.status_code != 200:
            raise JiraError(f"Jira request failed with status {resp.status_code}")

        return resp

    def _get(self, path: str, **kwargs) -> httpx.Response:
        resp = self._client.get(path, **kwargs)
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # search_issues
    # ------------------------------------------------------------------

    def search_issues(self, issue_keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch the current status for a batch of Jira issue keys via JQL.

        Args:
            issue_keys: Jira issue keys (e.g. `["ENG-1", "ENG-2"]`).

        Returns:
            `{issue_key: {"name": <status name>, "category": <statusCategory.key>}}`.
            Keys absent from Jira's response (deleted/moved issues) are
            simply omitted — this method never raises for a missing key.

        Raises:
            JiraAuthError: on 401/403.
            JiraTransientError: on 429 or 5xx.
        """
        if not issue_keys:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for start in range(0, len(issue_keys), self._SEARCH_BATCH_SIZE):
            chunk = issue_keys[start : start + self._SEARCH_BATCH_SIZE]
            results.update(self._search_issues_batch(chunk))
        return results

    def _search_issues_batch(self, keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """Run one JQL `issue in (...)` search (<=50 keys), paging until done."""
        jql = f"issue in ({', '.join(keys)})"
        results: Dict[str, Dict[str, Any]] = {}
        start_at = 0

        while True:
            resp = self._get(
                self._SEARCH_PATH,
                params={
                    "jql": jql,
                    "fields": "status",
                    "maxResults": self._SEARCH_PAGE_SIZE,
                    "startAt": start_at,
                },
            )
            data = resp.json()
            issues = data.get("issues") or []

            for issue in issues:
                key = issue.get("key")
                status = (issue.get("fields") or {}).get("status") or {}
                category = (status.get("statusCategory") or {}).get("key")
                results[key] = {"name": status.get("name"), "category": category}

            start_at += len(issues)
            total = data.get("total", start_at)
            if not issues or start_at >= total:
                break

        return results
