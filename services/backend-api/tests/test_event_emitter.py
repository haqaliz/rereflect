"""
TDD tests for event_emitter helper.

Tests cover:
- emit_event() wraps broadcast_to_org with correct event structure
- Timestamp field in ISO format
- Type/event_type fields
- Actor exclusion pass-through
"""

import pytest
from unittest.mock import AsyncMock, patch


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
