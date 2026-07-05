"""
Zendesk REST/incremental-export HTTP client for the zendesk-sync worker task
(ingestion-pull aspect).

Thin httpx wrapper, HTTP Basic auth using the token-access convention
(`{email}/token`, api_token) — mirrors src/clients/salesforce.py's structure
(context-manager, typed error taxonomy, token never logged/repr'd) and
services/backend-api/src/services/zendesk_client.py's auth scheme (a
*different*, backend-owned client used only for connect-time validate() —
see docs/planning/zendesk-integration/ingestion-pull/plan_20260705.md D4 for
why these are two separate classes in two separate services).

Pulls new/updated tickets via the incremental export endpoint
(`GET /api/v2/incremental/tickets?start_time=...&include=users`), paginating
via the literal `next_page` URL Zendesk returns until `end_of_stream`. The
side-loaded `users` array (from `include=users`) is merged onto each ticket
as a flat top-level `requester_email` key — the locked contract this task's
synthesized `event_data["ticket"]` must carry for `ZendeskAdapter` (see the
ingestion-core impl report's "Locked contracts" section).

R3: the api_token is stored on the instance but NEVER logged, and never
    appears in repr()/str().

Usage:
    with ZendeskClient(subdomain, email, api_token) as client:
        result = client.incremental_tickets(start_time=cursor_unix_ts)
        tickets = result["tickets"]
        new_cursor = result["end_time"]
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class ZendeskError(Exception):
    """Base class for all ZendeskClient errors."""


class ZendeskAuthError(ZendeskError):
    """Raised on 401/403 — invalid/expired token or insufficient permissions.

    Non-retrying: the Celery task must not call self.retry() on this, just
    record last_sync_status/last_error (D4 — a static API token auth
    failure is operator-recoverable, not a token-expiry event).
    """


class ZendeskTransientError(ZendeskError):
    """Raised on 429 / 5xx — caller (Celery task) should retry on this."""


class ZendeskNotFoundError(ZendeskError):
    """Raised on 404 — the requested resource doesn't exist."""


class ZendeskClient:
    """Thin httpx wrapper for Zendesk's incremental ticket export API."""

    # Cap pagination at 100 pages per run (mirrors Salesforce/HubSpot
    # clients). At 1000 tickets/page this is a pathological-volume safety
    # net, not an expected path — this pull task only ingests new tickets
    # from connection time forward (no historical backfill).
    PER_RUN_PAGE_CAP = 100

    def __init__(self, subdomain: str, email: str, api_token: str) -> None:
        # R3: token stored but NEVER logged / exposed via repr or str.
        self._subdomain = subdomain
        self._email = email
        self._api_token = api_token
        self._client = httpx.Client(
            base_url=f"https://{subdomain}.zendesk.com/api/v2",
            auth=(f"{email}/token", api_token),
            timeout=15.0,
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
    # Response -> error taxonomy
    # ------------------------------------------------------------------

    def _handle_response(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning(
                "zendesk_client: 429 rate limited; sleeping %ss", retry_after
            )
            time.sleep(retry_after)
            raise ZendeskTransientError(
                f"Zendesk rate limited, retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise ZendeskTransientError(f"Zendesk server error {resp.status_code}")

        if resp.status_code in (401, 403):
            raise ZendeskAuthError(f"Zendesk auth error (status {resp.status_code})")

        if resp.status_code == 404:
            raise ZendeskNotFoundError("Zendesk resource not found (status 404)")

        if resp.status_code != 200:
            raise ZendeskError(f"Zendesk request failed with status {resp.status_code}")

        return resp

    # ------------------------------------------------------------------
    # Incremental ticket export (paginated)
    # ------------------------------------------------------------------

    def incremental_tickets(self, start_time: int) -> Dict[str, Any]:
        """
        Poll `GET /incremental/tickets?start_time=...&include=users`,
        following the literal `next_page` URL Zendesk returns until
        `end_of_stream` is true (or PER_RUN_PAGE_CAP pages have been read).

        Side-loaded users (from `include=users`) are merged onto each
        ticket dict as a flat `requester_email` key (None if the ticket's
        `requester_id` has no matching side-loaded user).

        Returns:
            {"tickets": [...], "end_time": <unix ts of the last page read>}

        Raises:
            ZendeskAuthError: on 401/403.
            ZendeskTransientError: on 429 (after sleeping Retry-After
                seconds) or 5xx.
            ZendeskNotFoundError: on 404.
        """
        tickets: list = []
        end_time = start_time
        page_count = 0

        path: Optional[str] = "/incremental/tickets"
        params: Optional[Dict[str, Any]] = {"start_time": start_time, "include": "users"}
        next_url: Optional[str] = None

        while True:
            if page_count >= self.PER_RUN_PAGE_CAP:
                logger.warning(
                    "zendesk_client: per-run page cap reached — stopped "
                    "after %d pages (%d tickets); remaining tickets will "
                    "be picked up on the next scheduled sync",
                    page_count,
                    len(tickets),
                )
                break

            if next_url is not None:
                # Zendesk's own literal next_page URL — never reconstruct
                # start_time/cursor params ourselves.
                resp = self._client.get(next_url)
            else:
                resp = self._client.get(path, params=params)

            resp = self._handle_response(resp)
            data = resp.json()

            users_by_id = {u.get("id"): u for u in (data.get("users") or [])}
            for ticket in data.get("tickets", []):
                requester_id = ticket.get("requester_id")
                user = users_by_id.get(requester_id)
                ticket["requester_email"] = user.get("email") if user else None
                tickets.append(ticket)

            end_time = data.get("end_time", end_time)
            page_count += 1

            if data.get("end_of_stream"):
                break

            next_page = data.get("next_page")
            if not next_page:
                break

            next_url = next_page

        return {"tickets": tickets, "end_time": end_time}
