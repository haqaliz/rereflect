"""Tests for the IntercomClient conversation-parts access (client-conversation-parts
aspect).

Task 0 verified the API shape against Intercom's published OpenAPI specification
and adopted R1b: `display_as: "conversation_parts"` is NOT documented on
`POST /conversations/search` (the only documented `display_as` value is
`plaintext`, on the detail GET), and search items do not carry
`conversation_parts`. So this file pins the fallback: `get_conversation` ->
`GET /conversations/{id}`, whose `conversation_parts.conversation_parts[]` is the
exact key path `adapter.fetch_context` already consumes.

Decision record: spec.md "Task 0 decision record (2026-08-15)".

Modelled on TestIntercomClientSearch in tests/test_intercom_sync.py and the
write-client tests: every case drives the REAL request-building code through
httpx.MockTransport injected via the client's `transport` param -- no patch() of
the client, no real network. The transport-injection case is deliberately
redundant: it pins the acceptance criterion that the injected transport is what
actually carries the request.

The fixture shapes are the cross-aspect contract the adapter aspect mirrors (its
spec: "fixtures mirror exactly" these) -- do not drift them independently.

See docs/planning/intercom-pull-replies-and-ratings/client-conversation-parts/.
"""
from __future__ import annotations


def _part(part_id, part_type="comment", body="That fixed it, thanks!",
          author=None, created_at=1785400100):
    """One conversation part as the detail-shaped response carries it."""
    return {
        "type": "conversation_part",
        "id": part_id,
        "part_type": part_type,
        "body": f"<p>{body}</p>",
        "created_at": created_at,
        "author": author or {
            "type": "user",
            "id": "contact_c1",
            "name": "Dana Okafor",
            "email": "dana@example.com",
        },
    }


def _rating(score=5, remark="Quick fix", rated_at=1785400120):
    """Top-level rating object on a detail-shaped conversation."""
    return {"type": "conversation_rating", "rating": score,
            "remark": remark, "created_at": rated_at}


def _conversation_with_parts(conv_id="c1", body="Billing is broken",
                             email="dana@example.com", updated_at=1785400000,
                             parts=None, rating=None):
    """Search result in `display_as="conversation_parts"` shape: the existing
    `source`-shape conversation (test_intercom_sync.py `_conversation`) PLUS
    `conversation_parts` and an optional top-level `rating`."""
    conv = {
        "type": "conversation",
        "id": conv_id,
        "created_at": updated_at - 10,
        "updated_at": updated_at,
        "source": {
            "type": "conversation",
            "id": f"msg_{conv_id}",
            "body": f"<p>{body}</p>",
            "author": {
                "type": "user", "id": f"contact_{conv_id}",
                "name": "Dana Okafor", "email": email,
            },
        },
        "conversation_parts": {
            "type": "conversation_parts.list",
            "conversation_parts": parts or [],
            "total_count": len(parts or []),
        },
    }
    if rating is not None:
        conv["rating"] = rating
    return conv


# ──────────────────────── Detail fetch: shape ───────────────────────────────


class TestIntercomClientGetConversation:
    def test_get_conversation_gets_detail_url(self):
        """GET /conversations/{id} with Bearer auth returns the RAW detail
        payload -- parts + rating intact, no `_normalize` applied (unlike
        search, which adds `conversation_message` from `source`)."""
        import httpx

        from src.clients.intercom import IntercomClient

        payload = _conversation_with_parts(
            parts=[_part("part_1"), _part("part_2")], rating=_rating()
        )
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=payload)

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        result = client.get_conversation("c1")

        assert captured["method"] == "GET"
        assert captured["url"] == "https://api.intercom.io/conversations/c1"
        assert captured["auth"] == "Bearer tok"
        assert result == payload
        assert result["conversation_parts"]["conversation_parts"][0]["body"] == (
            "<p>That fixed it, thanks!</p>"
        )
        assert result["rating"]["rating"] == 5
        assert "conversation_message" not in result

    def test_get_conversation_404_raises_not_found_error(self):
        """404 -> IntercomNotFoundError, NOT IntercomAuthError: a conversation
        deleted between search and detail fetch is an idempotent noop for the
        caller, never an auth failure."""
        import httpx

        import pytest

        from src.clients.intercom import (
            IntercomAuthError,
            IntercomClient,
            IntercomError,
            IntercomNotFoundError,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"type": "error.list"})

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomNotFoundError) as excinfo:
            client.get_conversation("c1")

        assert isinstance(excinfo.value, IntercomError)
        assert not isinstance(excinfo.value, IntercomAuthError)

    def test_get_conversation_401_raises_auth_error(self):
        import httpx

        import pytest

        from src.clients.intercom import IntercomAuthError, IntercomClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errors": [{"code": "unauthorized"}]})

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomAuthError):
            client.get_conversation("c1")

    def test_get_conversation_429_raises_transient_error(self):
        import httpx

        import pytest

        from src.clients.intercom import IntercomClient, IntercomTransientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "30"})

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomTransientError):
            client.get_conversation("c1")

    def test_get_conversation_5xx_raises_transient_error(self):
        import httpx

        import pytest

        from src.clients.intercom import IntercomClient, IntercomTransientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomTransientError):
            client.get_conversation("c1")

    def test_get_conversation_network_error_raises_transient_error(self):
        """A transport-level failure (no HTTP response) -> IntercomTransientError,
        matching the write-surface contract."""
        import httpx

        import pytest

        from src.clients.intercom import IntercomClient, IntercomTransientError

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.HTTPError("Connection failed")

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomTransientError):
            client.get_conversation("c1")

    def test_get_conversation_transport_injection_is_used(self):
        """The injected MockTransport is what drives the real request-building
        code: a captured request proves the GET went through it."""
        import httpx

        from src.clients.intercom import IntercomClient

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["hit"] = True
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_conversation_with_parts())

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        client.get_conversation("c1")

        assert captured["hit"] is True
        assert captured["url"] == "https://api.intercom.io/conversations/c1"
