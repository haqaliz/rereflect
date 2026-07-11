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
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def text_to_adf(text: str) -> dict:
    """
    Build a minimal valid Atlassian Document Format (ADF) doc from plain text.

    Jira Cloud's `description` field (on `POST /issue`) requires ADF, not a
    plain string. Empty/None text still produces a valid ADF doc — a
    paragraph with no content — never an empty text node (Jira rejects
    `{"type": "text", "text": ""}`).
    """
    content = [{"type": "text", "text": text}] if text else []
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": content,
            }
        ],
    }


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

    @staticmethod
    def _assert_safe_site_url(site_url: str) -> None:
        """
        Defense-in-depth SSRF guard on the target host (SSRF finding, MEDIUM).

        The connect route is the primary gate (it canonicalizes + resolves the
        host and rejects private/link-local addresses); this asserts the invariant
        the client depends on so a JiraClient can never be pointed at an arbitrary
        or non-https host, even if constructed from another code path.

        String-level only (scheme + host suffix) — DNS resolution / private-IP
        rejection lives in the route to keep this class unit-testable without
        network I/O.
        """
        parsed = urlparse(site_url)
        if parsed.scheme != "https":
            raise ValueError("site_url must use https")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host.endswith(".atlassian.net"):
            raise ValueError("site_url must be a *.atlassian.net host")

    def __init__(self, site_url: str, email: str, api_token: str) -> None:
        """
        Args:
            site_url: already-canonicalized `https://{site}.atlassian.net`
                (normalization + DNS/IP SSRF checks are the connect route's
                responsibility; the client re-asserts the https + host-suffix
                invariant as defense-in-depth).
            email: the Atlassian account email used for Basic auth.
            api_token: the Atlassian API token used for Basic auth. Stored
                privately and never logged/repr'd.
        """
        self._assert_safe_site_url(site_url)
        # Token stored but NEVER logged / exposed via repr or str.
        self._site_url = site_url
        self._email = email
        self._api_token = api_token
        self._client = httpx.Client(
            base_url=f"{site_url}{self.API_PATH}",
            auth=(email, api_token),
            timeout=15.0,
            follow_redirects=False,
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

    # ------------------------------------------------------------------
    # get_projects / get_issue_types / create_issue (backend-create-issue)
    # ------------------------------------------------------------------

    def get_projects(self) -> list[dict]:
        """
        Return the Jira Cloud projects visible to the connected account via
        `GET /project/search`.

        Returns:
            list of `{id, key, name}` dicts.

        Raises:
            JiraAuthError: on 401/403.
            JiraTransientError: on 429 or 5xx.
        """
        resp = self._get("/project/search")
        data = resp.json()
        values = data.get("values", data) if isinstance(data, dict) else data
        return [
            {
                "id": project.get("id"),
                "key": project.get("key"),
                "name": project.get("name"),
            }
            for project in (values or [])
        ]

    def get_issue_types(self, project_id: str) -> list[dict]:
        """
        Return the issue types available for creation on `project_id`, via
        the project-scoped create-metadata endpoint
        `GET /issue/createmeta/{project_id}/issuetypes`.

        Tolerates an empty/missing list (some Jira configs return none for a
        given project) rather than raising.

        Returns:
            list of `{id, name}` dicts (possibly empty).

        Raises:
            JiraAuthError: on 401/403.
            JiraTransientError: on 429 or 5xx.
        """
        resp = self._get(f"/issue/createmeta/{project_id}/issuetypes")
        data = resp.json()
        values = data.get("issueTypes", data) if isinstance(data, dict) else data
        return [
            {
                "id": issue_type.get("id"),
                "name": issue_type.get("name"),
            }
            for issue_type in (values or [])
        ]

    # ------------------------------------------------------------------
    # search_issues (inbound status sync, Phase 3)
    # ------------------------------------------------------------------

    # NOTE endpoint choice: Jira Cloud is migrating `GET /rest/api/3/search`
    # to `GET /rest/api/3/search/jql` (the old endpoint is slated for
    # deprecation). This client's base_url already includes `/rest/api/3`,
    # so this constant is the ONE place to flip to `"/search/jql"` if/when
    # Atlassian sunsets the old shape — the request/param building below
    # doesn't otherwise need to change.
    _SEARCH_PATH = "/search"

    # Jira Cloud JQL search caps results per page; page through with
    # startAt/maxResults until every issue has been collected.
    _SEARCH_PAGE_SIZE = 100

    # Cap the number of issue keys embedded in a single JQL `issue in (...)`
    # clause per call — callers with more keys are chunked internally and
    # the per-chunk results are merged.
    _SEARCH_BATCH_SIZE = 50

    def search_issues(self, issue_keys: list[str]) -> dict:
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

        results: dict = {}
        for start in range(0, len(issue_keys), self._SEARCH_BATCH_SIZE):
            chunk = issue_keys[start : start + self._SEARCH_BATCH_SIZE]
            results.update(self._search_issues_batch(chunk))
        return results

    def _search_issues_batch(self, keys: list[str]) -> dict:
        """Run one JQL `issue in (...)` search (<=50 keys), paging until done."""
        jql = f"issue in ({', '.join(keys)})"
        results: dict = {}
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

    def create_issue(self, issue: dict) -> dict:
        """
        Create a Jira issue via `POST /issue`.

        Args:
            issue: dict with `project_id`, `issue_type_id`, `summary`
                (caller is responsible for the 255 char cap and non-empty
                validation) and `description_adf` (an Atlassian Document
                Format dict, e.g. the output of `text_to_adf`).

        Returns:
            dict with `id`, `key`, and `url` (the browse URL, built as
            `{site_url}/browse/{key}`).

        Raises:
            JiraAuthError: on 401/403 (stale/invalid token or insufficient
                project permissions).
            JiraTransientError: on 429 or 5xx.
        """
        payload = {
            "fields": {
                "project": {"id": issue["project_id"]},
                "issuetype": {"id": issue["issue_type_id"]},
                "summary": issue["summary"],
                "description": issue["description_adf"],
            }
        }
        resp = self._post("/issue", json=payload)
        data = resp.json()
        key = data.get("key")
        return {
            "id": data.get("id"),
            "key": key,
            "url": f"{self._site_url}/browse/{key}",
        }
