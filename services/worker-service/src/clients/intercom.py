"""Intercom REST client for the conversation-pull path.

Mirrors src/clients/zendesk.py in error taxonomy and lifecycle. Lives in
worker-service because worker-service cannot import backend-api; the backend
has its own minimal client for connection validation only.

Fixed host `api.intercom.io` -- no per-org subdomain, so no SSRF DNS gate is
needed here (the same reasoning recorded for Asana's fixed app.asana.com).

See docs/planning/intercom-selfhost-ingestion/pull-sync/.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

INTERCOM_API_BASE = "https://api.intercom.io"

# Intercom caps search at 150 per page. Stay under it -- a smaller page means a
# shorter transaction per round trip, and the pull is not latency-sensitive.
DEFAULT_PER_PAGE = 100
_TIMEOUT_SECONDS = 30.0


class IntercomError(Exception):
    """Base class for all IntercomClient errors."""


class IntercomAuthError(IntercomError):
    """Token rejected (401/403).

    Operator-recoverable and non-transient: the caller records it and stops,
    without retrying and without deactivating the integration.
    """


class IntercomTransientError(IntercomError):
    """Upstream 5xx, 429 or a network failure. Retrying is appropriate."""


class IntercomClient:
    def __init__(self, access_token: str, transport: Optional[Any] = None) -> None:
        self._access_token = access_token
        # `transport` exists so tests can drive the real request-building code
        # through httpx.MockTransport rather than mocking the method away --
        # the query body shape is part of this module's contract.
        self._client = httpx.Client(
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
        )

    def __enter__(self) -> "IntercomClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # pragma: no cover - never mask a real error
            logger.debug("Failed to close Intercom client", exc_info=True)

    def __repr__(self) -> str:  # never expose the token
        return "<IntercomClient>"

    __str__ = __repr__

    def _handle(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise IntercomAuthError(
                f"Intercom rejected the access token ({resp.status_code})"
            )
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise IntercomTransientError(
                f"Intercom rate limit hit (Retry-After: {retry_after})"
            )
        if resp.status_code >= 500:
            raise IntercomTransientError(f"Intercom returned {resp.status_code}")
        if resp.status_code >= 400:
            raise IntercomAuthError(f"Unexpected Intercom response {resp.status_code}")
        return resp

    def search_conversations(
        self,
        updated_since: int,
        starting_after: Optional[str] = None,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """One page of conversations updated at or after `updated_since`.

        Returns (conversations, next_cursor). `next_cursor` is None on the last
        page.

        The operator is `>=`, not `>`, on purpose. Unlike Zendesk's incremental
        endpoint there is no authoritative `end_time` watermark here, so the
        caller derives the next cursor from the maximum `updated_at` it saw. A
        strict `>` would silently drop any conversation sharing that exact
        second but returned after the page cap. `>=` cannot lose one; it merely
        re-fetches the boundary conversation, which FeedbackSourceEvent dedup
        discards.
        """
        body: Dict[str, Any] = {
            "query": {
                "field": "updated_at",
                "operator": ">=",
                "value": int(updated_since),
            },
            "pagination": {"per_page": per_page},
            "sort": {"field": "updated_at", "order": "ascending"},
        }
        if starting_after:
            body["pagination"]["starting_after"] = starting_after

        try:
            resp = self._client.post(
                f"{INTERCOM_API_BASE}/conversations/search",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise IntercomTransientError(str(exc)) from exc

        payload = self._handle(resp).json()
        conversations = [
            self._normalize(c) for c in (payload.get("conversations") or [])
        ]
        next_cursor = (
            (payload.get("pages") or {}).get("next", {}) or {}
        ).get("starting_after")

        return conversations, next_cursor

    @staticmethod
    def _normalize(conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Shape a search result like the webhook envelope's `data.item`.

        IntercomAdapter's contract is the WEBHOOK payload, which carries the
        first message under `conversation_message`. The search API returns the
        same content under `source`. Normalizing here -- rather than teaching
        the adapter a second shape -- keeps pull and webhook on one extraction
        path, which is the whole reason this feature has a shared dedup core.
        """
        normalized = dict(conversation)
        if "conversation_message" not in normalized and normalized.get("source"):
            normalized["conversation_message"] = normalized["source"]
        return normalized
