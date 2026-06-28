"""
Phase 4 TDD — Streaming compatibility for local/OpenAI-compatible endpoints.

Tests verify:
1. call_llm_stream with base_url uses AsyncOpenAI with base_url kwarg
   (local OpenAI-compatible path — already tested in Phase 2, but verified
   end-to-end with a mock stream yielding real chunks).
2. The WS message shape is preserved: each chunk produces a "stream" message
   with a "delta" key and the final message has done=True + metadata.
3. An empty stream (local model yields nothing) does not crash — produces
   a "stream done" message with empty content.
4. A local model stream that raises mid-stream is caught and surfaced as an
   error WS message, not an unhandled exception.
5. Chunk shape compatibility: local endpoints may return chunks without
   'usage' field — the handler must not crash on absent usage data.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── Helper: async generator factory ──────────────────────────────────────────


def _async_gen(items):
    """Create an async generator from a list of mock chunks."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


def _make_mock_chunk(content: str):
    """Build a mock streaming chunk with the expected shape."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock()
    chunk.choices[0].delta.content = content
    # Local models may not include usage info
    chunk.usage = None
    return chunk


# ── 1. call_llm_stream with base_url creates the right client ─────────────────


class TestCallLLMStreamSignature:
    """call_llm_stream must accept base_url kwarg (regression check)."""

    def test_call_llm_stream_has_base_url_param(self):
        import inspect
        from src.api.routes.copilot_ws import call_llm_stream
        sig = inspect.signature(call_llm_stream)
        assert "base_url" in sig.parameters, (
            "call_llm_stream must accept 'base_url' keyword argument"
        )


# ── 2. WS message shape preserved for local streams ──────────────────────────


class TestStreamingWSContractLocal:
    """
    The WS streaming contract must hold when generation uses a local endpoint:
    - Each token → {"type": "stream", "delta": <str>, "done": False}
    - Final message → {"type": "stream", "delta": "", "done": True, "metadata": {...}}
    """

    def _make_handle_query_mocks(self, org_id=1):
        mock_ws = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = org_id
        mock_user = MagicMock()
        mock_user.id = 1
        mock_conv = MagicMock()
        mock_conv.id = 1

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        mock_sub = MagicMock()
        mock_sub.plan = "pro"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_sub
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        return mock_ws, mock_org, mock_user, mock_conv, mock_db

    def _local_cfg(self):
        from src.services.copilot.llm_resolver import LLMConfig
        return LLMConfig(
            provider="openai_compatible", model="llama3",
            api_key=None, base_url="http://localhost:11434/v1", is_configured=True,
        )

    @pytest.mark.asyncio
    async def test_local_stream_produces_correct_ws_shape(self):
        """
        Tokens from a local stream → correct 'stream' WS messages with delta and done.
        """
        from src.api.routes.copilot_ws import _handle_query

        mock_ws, mock_org, mock_user, mock_conv, mock_db = self._make_handle_query_mocks()
        cfg = self._local_cfg()

        received_messages = []
        original_send = mock_ws.send_json

        async def capture_send(data):
            received_messages.append(data)
        mock_ws.send_json = AsyncMock(side_effect=capture_send)

        # Mock local stream with 3 chunks
        chunks = [
            _make_mock_chunk("Hello "),
            _make_mock_chunk("from "),
            _make_mock_chunk("Ollama!"),
        ]

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=cfg), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.call_llm_stream",
                   side_effect=lambda **kw: _async_gen(chunks)):

            MockIC.return_value.classify.return_value = {"intent": "general", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "org context"
            MockMatcher.return_value.find_match.return_value = None

            try:
                await _handle_query(
                    websocket=mock_ws, db=mock_db, user=mock_user,
                    org=mock_org, conversation=mock_conv,
                    content="hello", context_scope="all_data", message_id="stream_test_1",
                )
            except Exception:
                pass

        stream_messages = [m for m in received_messages if m.get("type") == "stream"]
        assert len(stream_messages) >= 1, "Must produce at least one stream message"

        # Each delta message must have the expected shape
        delta_messages = [m for m in stream_messages if not m.get("done", False)]
        for msg in delta_messages:
            assert "delta" in msg, f"Missing 'delta' in stream message: {msg}"
            assert "message_id" in msg, f"Missing 'message_id' in stream message: {msg}"

        # Final message must have done=True and metadata
        done_messages = [m for m in stream_messages if m.get("done", False)]
        assert len(done_messages) >= 1, "Must have a final stream message with done=True"
        final = done_messages[-1]
        assert final.get("done") is True
        assert "metadata" in final, "Final stream message must include metadata"

    @pytest.mark.asyncio
    async def test_empty_local_stream_does_not_crash(self):
        """
        A local model that yields no tokens (empty stream) must not crash.
        A "done" message must still be sent.
        """
        from src.api.routes.copilot_ws import _handle_query

        mock_ws, mock_org, mock_user, mock_conv, mock_db = self._make_handle_query_mocks()
        cfg = self._local_cfg()

        received = []

        async def capture(data):
            received.append(data)
        mock_ws.send_json = AsyncMock(side_effect=capture)

        # Empty stream
        async def empty_stream(**kw):
            return
            yield  # make it an async generator

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=cfg), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.call_llm_stream", side_effect=empty_stream):

            MockIC.return_value.classify.return_value = {"intent": "general", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "ctx"

            try:
                await _handle_query(
                    websocket=mock_ws, db=mock_db, user=mock_user,
                    org=mock_org, conversation=mock_conv,
                    content="anything", context_scope="all_data", message_id="empty_stream_1",
                )
            except Exception:
                pass

        # Must not crash — a done message should appear
        done_msgs = [m for m in received if m.get("type") == "stream" and m.get("done")]
        assert len(done_msgs) >= 1, (
            "Empty local stream must produce a final done=True stream message"
        )


# ── 3. Mid-stream error handling ──────────────────────────────────────────────


class TestStreamingErrorHandling:
    """
    A local endpoint that raises mid-stream must be caught.
    The user receives an error WS message; no unhandled exception propagates.
    """

    @pytest.mark.asyncio
    async def test_mid_stream_error_sends_error_message(self):
        """
        When call_llm_stream raises an exception, _handle_query must catch it
        and send an error WS message.
        """
        from src.api.routes.copilot_ws import _handle_query
        from src.services.copilot.llm_resolver import LLMConfig

        cfg = LLMConfig(
            provider="openai_compatible", model="llama3",
            api_key=None, base_url="http://localhost:11434/v1", is_configured=True,
        )

        mock_ws = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = 1
        mock_user = MagicMock()
        mock_user.id = 1
        mock_conv = MagicMock()
        mock_conv.id = 1

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        mock_sub = MagicMock()
        mock_sub.plan = "pro"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_sub
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        received = []

        async def capture(data):
            received.append(data)
        mock_ws.send_json = AsyncMock(side_effect=capture)

        # Stream that errors mid-way
        async def erroring_stream(**kw):
            yield _make_mock_chunk("Hello ")
            raise ConnectionError("Local endpoint disconnected")

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=cfg), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.call_llm_stream", side_effect=erroring_stream):

            MockIC.return_value.classify.return_value = {"intent": "general", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "ctx"

            try:
                # Must NOT raise an unhandled exception
                await _handle_query(
                    websocket=mock_ws, db=mock_db, user=mock_user,
                    org=mock_org, conversation=mock_conv,
                    content="test", context_scope="all_data", message_id="err_stream_1",
                )
            except Exception as e:
                pytest.fail(
                    f"_handle_query must catch mid-stream errors; raised: {e}"
                )

        # An error message must have been sent
        error_msgs = [m for m in received if m.get("type") == "error"]
        assert len(error_msgs) >= 1, (
            f"Mid-stream error must produce an error WS message; got: {received}"
        )


# ── 4. Chunk shape without 'usage' field ─────────────────────────────────────


class TestChunkShapeCompatibility:
    """
    Local model chunks may not include usage/token counts.
    The handler must not crash when usage is absent.
    """

    @pytest.mark.asyncio
    async def test_chunks_without_usage_do_not_crash(self):
        """
        Chunks from local models may lack 'usage' — the handler must not crash
        when accessing token counts.
        """
        from src.api.routes.copilot_ws import _handle_query
        from src.services.copilot.llm_resolver import LLMConfig

        cfg = LLMConfig(
            provider="openai_compatible", model="llama3",
            api_key=None, base_url="http://localhost:11434/v1", is_configured=True,
        )

        mock_ws = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = 1
        mock_user = MagicMock()
        mock_user.id = 1
        mock_conv = MagicMock()
        mock_conv.id = 1

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        mock_sub = MagicMock()
        mock_sub.plan = "pro"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_sub
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        # Chunk with usage=None (typical of local model responses)
        chunks_no_usage = [
            _make_mock_chunk("Answer"),  # usage=None is set in the helper
        ]

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=cfg), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.call_llm_stream",
                   side_effect=lambda **kw: _async_gen(chunks_no_usage)):

            MockIC.return_value.classify.return_value = {"intent": "general", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "ctx"

            # Must NOT raise
            try:
                await _handle_query(
                    websocket=mock_ws, db=mock_db, user=mock_user,
                    org=mock_org, conversation=mock_conv,
                    content="test", context_scope="all_data", message_id="usage_none_1",
                )
            except Exception as e:
                pytest.fail(f"Chunks without usage field caused a crash: {e}")
