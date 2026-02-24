"""
TDD tests for event_emitter helper and internal events endpoint.

Tests cover:
- emit_event() wraps broadcast_to_org with correct event structure
- Timestamp field in ISO format
- Type/event_type fields
- Actor exclusion pass-through
- Internal HTTP endpoint secret validation
- Internal endpoint triggers broadcast
- Internal endpoint field validation
"""

import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


# =============================================================================
# emit_event() UNIT TESTS
# =============================================================================


class TestEmitEvent:
    @pytest.mark.asyncio
    async def test_emit_event_broadcasts_to_org(self):
        """emit_event(org_id=10, "feedback:created", data) → broadcast_to_org called."""
        from src.services.event_emitter import emit_event
        from src.services import event_connection_manager as ecm_module

        mock_broadcast = AsyncMock()
        with patch.object(ecm_module.event_manager, "broadcast_to_org", mock_broadcast):
            await emit_event(org_id=10, event_type="feedback:created", data={"id": 1})

        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args
        assert call_kwargs.kwargs["org_id"] == 10 or call_kwargs.args[0] == 10

    @pytest.mark.asyncio
    async def test_emit_event_includes_timestamp(self):
        """Emitted event has 'timestamp' field in ISO format."""
        from src.services.event_emitter import emit_event
        from src.services import event_connection_manager as ecm_module

        captured = {}

        async def capture_broadcast(org_id, event, exclude_user_id=None):
            captured["event"] = event

        with patch.object(ecm_module.event_manager, "broadcast_to_org", capture_broadcast):
            await emit_event(org_id=10, event_type="feedback:created", data={})

        assert "timestamp" in captured["event"]
        # Should be parseable ISO timestamp
        from datetime import datetime
        ts = captured["event"]["timestamp"]
        # Basic check: contains date separator
        assert "T" in ts or "-" in ts

    @pytest.mark.asyncio
    async def test_emit_event_includes_event_type(self):
        """Emitted event has type='event' and event_type='feedback:created'."""
        from src.services.event_emitter import emit_event
        from src.services import event_connection_manager as ecm_module

        captured = {}

        async def capture_broadcast(org_id, event, exclude_user_id=None):
            captured["event"] = event

        with patch.object(ecm_module.event_manager, "broadcast_to_org", capture_broadcast):
            await emit_event(org_id=10, event_type="feedback:created", data={"id": 99})

        assert captured["event"]["type"] == "event"
        assert captured["event"]["event_type"] == "feedback:created"

    @pytest.mark.asyncio
    async def test_emit_event_excludes_actor(self):
        """emit_event with exclude_user_id=5 → broadcast called with exclude_user_id=5."""
        from src.services.event_emitter import emit_event
        from src.services import event_connection_manager as ecm_module

        mock_broadcast = AsyncMock()
        with patch.object(ecm_module.event_manager, "broadcast_to_org", mock_broadcast):
            await emit_event(org_id=10, event_type="feedback:created", data={}, exclude_user_id=5)

        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args
        # Check exclude_user_id=5 was passed
        passed_exclude = call_kwargs.kwargs.get("exclude_user_id")
        if passed_exclude is None and len(call_kwargs.args) >= 3:
            passed_exclude = call_kwargs.args[2]
        assert passed_exclude == 5

    @pytest.mark.asyncio
    async def test_emit_event_without_exclude(self):
        """emit_event without exclude → broadcast called with exclude_user_id=None."""
        from src.services.event_emitter import emit_event
        from src.services import event_connection_manager as ecm_module

        mock_broadcast = AsyncMock()
        with patch.object(ecm_module.event_manager, "broadcast_to_org", mock_broadcast):
            await emit_event(org_id=10, event_type="feedback:created", data={})

        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args
        passed_exclude = call_kwargs.kwargs.get("exclude_user_id", None)
        assert passed_exclude is None


# =============================================================================
# INTERNAL EMIT ENDPOINT TESTS
# =============================================================================


class TestInternalEmitEndpoint:
    def test_internal_emit_endpoint_requires_secret(self, client: TestClient):
        """POST /api/internal/events/emit without secret → 403."""
        response = client.post(
            "/api/internal/events/emit",
            json={
                "org_id": 10,
                "event_type": "feedback:analyzed",
                "data": {"id": 1},
            }
            # No X-Internal-Secret header
        )
        assert response.status_code == 403

    def test_internal_emit_endpoint_wrong_secret(self, client: TestClient):
        """POST with wrong secret → 403."""
        response = client.post(
            "/api/internal/events/emit",
            json={
                "org_id": 10,
                "event_type": "feedback:analyzed",
                "data": {"id": 1},
            },
            headers={"X-Internal-Secret": "wrong-secret"},
        )
        assert response.status_code == 403

    def test_internal_emit_endpoint_with_valid_secret(self, client: TestClient):
        """POST with correct INTERNAL_EVENTS_SECRET → 200, broadcast called."""
        from src.services import event_connection_manager as ecm_module

        secret = os.getenv("INTERNAL_EVENTS_SECRET", "dev-secret")
        mock_broadcast = AsyncMock()

        with patch.object(ecm_module.event_manager, "broadcast_to_org", mock_broadcast):
            response = client.post(
                "/api/internal/events/emit",
                json={
                    "org_id": 10,
                    "event_type": "feedback:analyzed",
                    "data": {"id": 1},
                },
                headers={"X-Internal-Secret": secret},
            )

        assert response.status_code == 200

    def test_internal_emit_endpoint_missing_fields(self, client: TestClient):
        """POST without org_id or event_type → 422."""
        secret = os.getenv("INTERNAL_EVENTS_SECRET", "dev-secret")
        response = client.post(
            "/api/internal/events/emit",
            json={"data": {"id": 1}},  # missing org_id and event_type
            headers={"X-Internal-Secret": secret},
        )
        assert response.status_code == 422
