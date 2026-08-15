"""Intercom REST client for the conversation-pull and write-back paths.

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


class IntercomNotFoundError(IntercomError):
    """Upstream 404 (conversation missing or already closed).

    Non-retryable and not an auth problem: the caller maps it to a noop
    (close is idempotent-by-404).
    """


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
        if resp.status_code == 404:
            raise IntercomNotFoundError(
                f"Intercom resource not found ({resp.status_code})"
            )
        # 404 must never reach this fallback: it is a first-class, distinct
        # error (see IntercomNotFoundError), not an auth problem. This branch
        # therefore only sees non-404 4xx.
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

    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Fetch one conversation's full detail payload.

        Returns the raw response object: `conversation_parts.conversation_parts[]`
        holds the reply parts and `rating` the satisfaction rating, parsed by the
        adapter, not here. 404 -> IntercomNotFoundError (caller: idempotent noop);
        401/403 -> IntercomAuthError; 429/5xx/network -> IntercomTransientError.
        """
        try:
            resp = self._client.get(
                f"{INTERCOM_API_BASE}/conversations/{conversation_id}",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise IntercomTransientError(str(exc)) from exc

        return self._handle(resp).json()

    def add_note(
        self, conversation_id: str, admin_id: str, body: str
    ) -> None:
        """Append an admin note to a conversation (write-back path).

        POST /conversations/{id}/reply with message_type=note. Returns None
        on success; the caller distinguishes success from failure purely by
        "no exception" -- 401/403 raise IntercomAuthError, 404 raises
        IntercomNotFoundError, 429/5xx/network raise IntercomTransientError.
        """
        try:
            resp = self._client.post(
                f"{INTERCOM_API_BASE}/conversations/{conversation_id}/reply",
                json={
                    "message_type": "note",
                    "type": "admin",
                    "admin_id": admin_id,
                    "body": body,
                },
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise IntercomTransientError(str(exc)) from exc

        self._handle(resp)

    def close_conversation(self, conversation_id: str, admin_id: str) -> None:
        """Close a conversation (write-back path).

        POST /conversations/{id}/parts with message_type=close. Returns None
        on success; same error contract as add_note. Closing an already-closed
        conversation surfaces as a 404 -> IntercomNotFoundError, which the
        caller treats as an idempotent noop.
        """
        try:
            resp = self._client.post(
                f"{INTERCOM_API_BASE}/conversations/{conversation_id}/parts",
                json={
                    "message_type": "close",
                    "type": "admin",
                    "admin_id": admin_id,
                },
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise IntercomTransientError(str(exc)) from exc

        self._handle(resp)

    def fetch_admin_id(self) -> str:
        """Resolve the authenticated admin's id from GET /me.

        Fallback when no admin_id is stored on the integration row. A 200
        whose payload lacks `id` raises base IntercomError: a malformed
        payload is neither retryable nor operator-scope, so the task records
        it as a failure without retrying.
        """
        try:
            resp = self._client.get(
                f"{INTERCOM_API_BASE}/me",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise IntercomTransientError(str(exc)) from exc

        payload = self._handle(resp).json()
        admin_id = payload.get("id")
        if not admin_id:
            raise IntercomError("Intercom /me response missing id")
        return admin_id

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
