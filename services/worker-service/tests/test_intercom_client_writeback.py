"""Tests for the IntercomClient write surface (write-back aspect).

IntercomClient gains `add_note`, `close_conversation` and `fetch_admin_id` so
the write-back task can annotate and close conversations from worker-service,
with the error taxonomy the old backend write-back module lacked: 401/403 ->
IntercomAuthError, 429/5xx/network -> IntercomTransientError, and a distinct
404 -> IntercomNotFoundError so "already closed / not found" is a noop, not a
confusing auth error.

Modelled on TestIntercomClientSearch in tests/test_intercom_sync.py: every
case drives the REAL request-building code through httpx.MockTransport
injected via the client's `transport` param -- no patch() of the client, no
real network. That is also what pins acceptance criterion "transport
injection works": if the client stopped honouring the injected transport,
every test here fails.

See docs/planning/intercom-writeback/worker-write-client/.
"""
from __future__ import annotations


def _make_client(handler):
    import httpx

    from src.clients.intercom import IntercomClient

    return IntercomClient("tok", transport=httpx.MockTransport(handler))


def _json_body(request):
    import json

    return json.loads(request.content)


# ──────────────────────── Write calls: shape ─────────────────────────────────


def test_add_note_posts_to_reply_url_with_exact_body():
    """R8 -- POST /conversations/{id}/reply with the Intercom admin-note
    payload, Bearer auth, None on success (raise-on-error contract)."""
    import httpx

    from src.clients.intercom import IntercomClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = _json_body(request)
        return httpx.Response(200, json={"type": "conversation"})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    result = client.add_note(
        "conv_123", "admin_1", "Feedback categorized as pain point."
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.intercom.io/conversations/conv_123/reply"
    assert captured["auth"] == "Bearer tok"
    assert captured["body"] == {
        "message_type": "note",
        "type": "admin",
        "admin_id": "admin_1",
        "body": "Feedback categorized as pain point.",
    }
    assert result is None


def test_close_conversation_posts_to_parts_url_with_exact_body():
    """R8 -- POST /conversations/{id}/parts with the close payload, None on
    success."""
    import httpx

    from src.clients.intercom import IntercomClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = _json_body(request)
        return httpx.Response(200, json={"type": "conversation"})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    result = client.close_conversation("conv_456", "admin_2")

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.intercom.io/conversations/conv_456/parts"
    assert captured["auth"] == "Bearer tok"
    assert captured["body"] == {
        "message_type": "close",
        "type": "admin",
        "admin_id": "admin_2",
    }
    assert result is None


def test_fetch_admin_id_returns_me_id():
    """R8 -- GET /me, return data["id"] (admin fallback when the stored
    admin_id is absent)."""
    import httpx

    from src.clients.intercom import IntercomClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": "admin_99", "type": "admin"})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    assert client.fetch_admin_id() == "admin_99"

    assert captured["method"] == "GET"
    assert captured["url"] == "https://api.intercom.io/me"
    assert captured["auth"] == "Bearer tok"


# ──────────────────────── Error taxonomy ────────────────────────────────────


def test_add_note_401_raises_auth_error():
    """401 -> IntercomAuthError: operator-recoverable scope problem, never a
    silent False."""
    import httpx

    import pytest

    from src.clients.intercom import IntercomAuthError, IntercomClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"code": "unauthorized"}]})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    with pytest.raises(IntercomAuthError):
        client.add_note("conv_123", "admin_1", "body")


def test_add_note_403_raises_auth_error():
    """403 (missing conversation:write scope) -> IntercomAuthError, per the
    prd.md R3.5 contract: recorded as missing_write_scope, never auto-disable."""
    import httpx

    import pytest

    from src.clients.intercom import IntercomAuthError, IntercomClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": [{"code": "forbidden"}]})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    with pytest.raises(IntercomAuthError):
        client.add_note("conv_123", "admin_1", "body")


def test_close_conversation_404_raises_not_found_error():
    """404 -> IntercomNotFoundError: distinguishable from IntercomAuthError so
    "already closed / not found" maps to a noop in the task, not an auth
    failure. The old _handle mislabeled every non-401 4xx as IntercomAuthError."""
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
        client.close_conversation("conv_456", "admin_2")

    assert isinstance(excinfo.value, IntercomError)
    assert not isinstance(excinfo.value, IntercomAuthError)


def test_fetch_admin_id_429_raises_transient_error():
    """429 -> IntercomTransientError: rate limit, retrying is correct."""
    import httpx

    import pytest

    from src.clients.intercom import IntercomClient, IntercomTransientError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    with pytest.raises(IntercomTransientError):
        client.fetch_admin_id()


def test_add_note_500_raises_transient_error():
    """5xx -> IntercomTransientError: upstream failure, retrying is correct."""
    import httpx

    import pytest

    from src.clients.intercom import IntercomClient, IntercomTransientError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    with pytest.raises(IntercomTransientError):
        client.add_note("conv_123", "admin_1", "body")


def test_add_note_network_error_raises_transient_error():
    """A transport-level failure (no HTTP response) -> IntercomTransientError.
    Ports the old service's `returns False` failure case under the new
    raise-on-error contract."""
    import httpx

    import pytest

    from src.clients.intercom import IntercomClient, IntercomTransientError

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.HTTPError("Connection failed")

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    with pytest.raises(IntercomTransientError):
        client.add_note("conv_123", "admin_1", "body")


def test_fetch_admin_id_missing_id_raises_base_error():
    """A 200 from /me without `id` is a malformed payload: base IntercomError,
    neither retryable nor auth -- the task records it as a failure and does
    not retry."""
    import httpx

    import pytest

    from src.clients.intercom import IntercomClient, IntercomError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    with pytest.raises(IntercomError):
        client.fetch_admin_id()


# ──────────────────────── Transport injection ───────────────────────────────


def test_transport_injection_is_used_for_write_calls():
    """The injected MockTransport is what drives the real request-building
    code: a captured request proves the write call went through it."""
    import httpx

    from src.clients.intercom import IntercomClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["hit"] = True
        captured["url"] = str(request.url)
        return httpx.Response(200, json={})

    client = IntercomClient("tok", transport=httpx.MockTransport(handler))
    client.add_note("conv_123", "admin_1", "body")

    assert captured["hit"] is True
    assert captured["url"] == "https://api.intercom.io/conversations/conv_123/reply"
